"""Pilnowanie ustawień falownika — "Pilnuj ustawień".

Problem który rozwiązuje ten moduł
-----------------------------------
Komenda do falownika idzie przez ``write_manager`` (execute → settle → verify →
ACK). Verify potwierdza tylko, że falownik przyjął wartość **w tym momencie**.
Ale Deye/Solarman po Modbusie potrafi po kilku–kilkunastu minutach SAM wrócić do
wcześniejszej wartości rejestru. Efekt: optymalizator zaplanował np. ładowanie z
sieci na drogą godzinę, komenda wykonała się i zweryfikowała OK, a 10 minut
później falownik cicho zresetował ustawienie — i plan nie jest realizowany.

Jak działa guard
----------------
1. Po każdej komendzie z backendu ``write_manager`` woła ``register_many`` —
   guard zapamiętuje "stan docelowy" każdej sterowanej encji.
2. Guard pilnuje tych encji DWOMA mechanizmami:
   a) **zdarzeniowo** — nasłuchuje ``state_changed`` i reaguje natychmiast gdy
      encja odejdzie od planu,
   b) **okresowo** (sweep co ``GUARD_SWEEP_INTERVAL`` s) — re-sprawdza wszystkie
      pilnowane encje. To łapie przypadek "falownik utknął na złej wartości bez
      emitowania zdarzenia" oraz cichą porażkę poprzedniej korekty — bo pojedynczy
      write nie daje pewności, że tym razem zadziałał.
3. Gdy encja odchyla się od planu, guard wrzuca do ``write_managera`` komendę
   przywracającą (z flagą ``guard`` → bez ACK do backendu, to korekta lokalna).

Dedup ``_pending``
------------------
Po wysłaniu korekty encja trafia do ``_pending``, żeby zdarzenia/sweep w trakcie
jej realizacji nie zakolejkowały duplikatów. ``write_manager`` po przetworzeniu
korekty woła ``on_correction_processed`` → encja wraca do gry. Dzięki temu guard
pilnuje DALEJ przez całą godzinę: jeśli wartość znów ucieknie (albo korekta
zawiodła), kolejne odchylenie wywoła nową korektę. Reset planu (nowe dane z
backendu) czyści ``_pending`` przez ``register_many``.

Wyłączenie
----------
Przełącznik "Pilnuj ustawień" (switch.py) ustawia ``coordinator_data`` →
``DATA_GUARD_ENABLED``. Gdy OFF, guard nie przywraca wartości (sweep i zdarzenia
kończą się wcześnie). Domyślnie ON — plan egzekwowany od razu po instalacji.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

from .const import DATA_GUARD_ENABLED, DEFAULT_GUARD_ENABLED, GUARD_SWEEP_INTERVAL
from .helpers import state_matches_expected

_LOGGER = logging.getLogger(__name__)

UNAVAILABLE_STATES = ("unknown", "unavailable")


class SettingsGuard:
    """Pilnuje, by sterowane encje trzymały wartość z planu przez całą godzinę.

    Jedna instancja per config entry — żyje w ``coordinator_data["settings_guard"]``.
    ``start()`` (z ``async_setup_entry``) uruchamia okresowy sweep; subskrypcja
    zdarzeń tworzy się leniwie przy pierwszej zarejestrowanej encji. ``stop()``
    (z ``async_unload_entry``) odpina oba nasłuchy.
    """

    def __init__(self, hass: HomeAssistant, coordinator_data: dict[str, Any]) -> None:
        """Zainicjalizuj puste rejestry — nasłuchy startują dopiero w ``start()``."""
        self.hass = hass
        self.coordinator_data = coordinator_data
        # entity_id → komenda przywracająca {entity_id, domain, service, service_data}
        self._desired: dict[str, dict[str, Any]] = {}
        # encje z korektą w locie (dedup) — czyszczone przez on_correction_processed
        self._pending: set[str] = set()
        self._unsub_state = None
        self._unsub_sweep = None

    # === API publiczne ===

    def start(self) -> None:
        """Uruchom okresowy sweep. Bezpieczne do wielokrotnego wywołania."""
        if self._unsub_sweep is None:
            self._unsub_sweep = async_track_time_interval(
                self.hass, self._sweep, timedelta(seconds=GUARD_SWEEP_INTERVAL)
            )

    def stop(self) -> None:
        """Odepnij nasłuch zdarzeń i sweep (przy unload integracji)."""
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None
        if self._unsub_sweep:
            self._unsub_sweep()
            self._unsub_sweep = None

    def is_enabled(self) -> bool:
        """Czy przełącznik "Pilnuj ustawień" jest włączony."""
        return bool(self.coordinator_data.get(DATA_GUARD_ENABLED, DEFAULT_GUARD_ENABLED))

    def register_many(self, commands: list[dict[str, Any]]) -> None:
        """Zapamiętaj docelowy stan encji z batcha komend backendu.

        Wołane przez ``write_manager`` po przetworzeniu batcha. Rejestrujemy każdą
        komendę (też tę z nieudanym verify — chcemy DALEJ dążyć do planu).
        Świeży plan z backendu czyści ``_pending`` dla tych encji.
        """
        added = False
        for cmd in commands:
            entity_id = cmd.get("entity_id")
            service = cmd.get("service")
            if not entity_id or not service:
                continue
            if entity_id not in self._desired:
                added = True
            self._desired[entity_id] = {
                "entity_id": entity_id,
                "domain": cmd.get("domain"),
                "service": service,
                "service_data": dict(cmd.get("service_data") or {}),
            }
            self._pending.discard(entity_id)
        if added:
            self._resubscribe()
        if commands:
            _LOGGER.debug("Guard pilnuje %d encji", len(self._desired))

    def on_correction_processed(self, entity_id: str | None) -> None:
        """``write_manager`` skończył przetwarzać korektę guarda dla tej encji.

        Zdejmujemy z ``_pending`` niezależnie od wyniku — jeśli wartość dalej jest
        zła (korekta zawiodła), następne zdarzenie/sweep spróbuje ponownie.
        """
        if entity_id:
            self._pending.discard(entity_id)

    def clear_pending(self) -> None:
        """Wyczyść znaczniki korekt w locie (np. przy wyłączeniu przełącznika)."""
        self._pending.clear()

    # === Wewnętrzne: nasłuch + enforcement ===

    def _resubscribe(self) -> None:
        """(Re)subskrybuj zdarzenia ``state_changed`` dla aktualnego zbioru encji."""
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None
        if self._desired:
            self._unsub_state = async_track_state_change_event(
                self.hass, list(self._desired.keys()), self._handle_state_change
            )

    @callback
    def _handle_state_change(self, event: Event) -> None:
        """Reaguj natychmiast gdy pilnowana encja zmieni stan."""
        if not self.is_enabled():
            return
        entity_id = event.data.get("entity_id")
        cmd = self._desired.get(entity_id)
        if not cmd:
            return
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in UNAVAILABLE_STATES:
            return
        self._maybe_correct(entity_id, cmd, new_state.state)

    @callback
    def _sweep(self, now: Any = None) -> None:
        """Okresowo re-sprawdź wszystkie pilnowane encje (łapie ciche odchylenia)."""
        if not self.is_enabled():
            return
        for entity_id, cmd in list(self._desired.items()):
            state_obj = self.hass.states.get(entity_id)
            if state_obj is None or state_obj.state in UNAVAILABLE_STATES:
                continue
            self._maybe_correct(entity_id, cmd, state_obj.state)

    def _maybe_correct(self, entity_id: str, cmd: dict[str, Any], actual: str) -> None:
        """Jeśli ``actual`` odbiega od planu i nie ma korekty w locie — zakolejkuj ją."""
        if entity_id in self._pending:
            return
        ok, reason = state_matches_expected(cmd["service"], cmd["service_data"], actual)
        if ok:
            return
        write_manager = self.coordinator_data.get("write_manager")
        if not write_manager:
            return
        self._pending.add(entity_id)
        _LOGGER.warning(
            "Pilnuj ustawień: %s odeszło od planu (%s) — przywracam wartość", entity_id, reason
        )
        write_manager.enqueue([{**cmd, "guard": True}])
