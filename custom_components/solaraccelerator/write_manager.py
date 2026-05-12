"""Kolejka write — serializacja komend wysyłanych do falownika.

Problem który rozwiązuje ten moduł
----------------------------------
Backend wysyła komendy do HA przez kanał live (lista ``pending_commands``).
Aktualnie potrafi przyjść kilka komend w jednej odpowiedzi — np. zmiana mocy
ładowania, ustawienie progu SOC i przełączenie trybu pracy naraz.

Jeśli wszystkie wywołamy ``hass.services.async_call`` jedna po drugiej (nawet
sekwencyjnie z ``blocking=True``), to dla falownika Deye/Solarman po Modbusie
oznacza serię write w odstępach milisekund. Falownik **nie nadąża** i część
write jest odrzucana — komenda "znika" mimo że HA pokazuje że wykonała się OK.

Jak działa write manager
------------------------
1. ``live_loop`` dostaje batch ``pending_commands`` i woła ``WriteManager.enqueue(...)`` —
   batch ląduje w kolejce i live_loop wraca do pchania pushów (nie blokuje się).

2. Worker w tle pobiera batch z kolejki i przetwarza ją:
   a) wykonuje komendy po kolei z opóźnieniem ``command_delay`` między każdą,
   b) po ostatniej komendzie czeka ``verify_settling`` aż falownik się ustabilizuje,
   c) odczytuje wartości encji których komendy dotyczyły i porównuje z oczekiwanymi,
   d) wysyła ACK do backendu — success=True tylko gdy verify się powiódł.

Oba delay'e (``command_delay`` i ``verify_settling``) są czytane z encji typu
``number`` zdefiniowanych w ``number.py``. Użytkownik może je tunować z UI bez
restartu integracji.

Verify
------
Heurystyka po ``service`` name:
- ``number.set_value`` — porównujemy state == value (tolerancja 1.0),
- ``select.select_option`` — porównujemy state == option,
- ``switch.turn_on`` / ``turn_off`` — porównujemy state == "on" / "off",
- inne domeny — pomijamy verify (warning w logu), zwracamy success=True.

Deduplikacja cmd_id NIE jest robiona — backend wysyła komendy raz na godzinę,
więc ryzyko duplikatu jest minimalne (verify zwykle kończy się w ~10s).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import async_ack_command
from .const import (
    DEFAULT_COMMAND_DELAY,
    DEFAULT_VERIFY_SETTLING,
)

_LOGGER = logging.getLogger(__name__)


class WriteManager:
    """Kolejka komend do falownika z worker'em w tle.

    Tworzymy jedną instancję per config entry — żyje w ``coordinator_data["write_manager"]``.
    Worker startuje przy ``start()`` (wołane z ``async_setup_entry``) i kończy się
    przy ``stop()`` (wołane z ``async_unload_entry``).
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator_data: dict[str, Any],
    ) -> None:
        """Zainicjalizuj kolejkę i puste pola — worker nie startuje od razu."""
        self.hass = hass
        self.entry = entry
        self.coordinator_data = coordinator_data
        self._queue: asyncio.Queue[list[dict[str, Any]]] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

    # === API publiczne ===

    def start(self) -> None:
        """Uruchom worker'a w tle. Bezpieczne do wielokrotnego wywołania."""
        if self._worker_task and not self._worker_task.done():
            return
        self._worker_task = self.hass.async_create_task(self._worker())

    def stop(self) -> None:
        """Zatrzymaj worker'a (np. przy unload integracji)."""
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()

    def enqueue(self, commands: list[dict[str, Any]]) -> None:
        """Wrzuć batch komend do kolejki — wraca natychmiast, nie blokuje wołającego.

        Komendy bez ``id`` są pomijane (nie da się zrobić ACK bez identyfikatora).
        """
        valid = [c for c in commands if c.get("id")]
        if not valid:
            return
        self._queue.put_nowait(valid)
        _LOGGER.debug("Dodano batch %d komend do kolejki write", len(valid))

    # === Worker i przetwarzanie batchy ===

    async def _worker(self) -> None:
        """Pętla worker'a — przetwarza batche jedna po drugiej."""
        _LOGGER.debug("Worker write_managera wystartował")
        while True:
            try:
                batch = await self._queue.get()
                await self._process_batch(batch)
                self._queue.task_done()
            except asyncio.CancelledError:
                _LOGGER.debug("Worker write_managera anulowany")
                break
            except Exception as e:
                _LOGGER.exception("Nieoczekiwany błąd w workerze write_managera: %s", e)
                # Krótka pauza, żeby przy długotrwałym błędzie nie spalić CPU w pętli
                await asyncio.sleep(1)

    async def _process_batch(self, batch: list[dict[str, Any]]) -> None:
        """Wykonaj jedną batch komend zgodnie z planem: execute → settle → verify → ACK."""
        command_delay = self._get_command_delay()
        verify_settling = self._get_verify_settling()

        _LOGGER.info(
            "Przetwarzam batch %d komend (delay=%.2fs, settling=%.2fs)",
            len(batch), command_delay, verify_settling,
        )

        # Krok 1: wykonaj wszystkie komendy z pauzą między nimi
        execute_results: list[tuple[bool, str | None]] = []
        for i, cmd in enumerate(batch):
            success, error = await self._execute_one(cmd)
            execute_results.append((success, error))

            # Pauza po każdej oprócz ostatniej — po ostatniej dajemy settling
            if i < len(batch) - 1:
                await asyncio.sleep(command_delay)

        # Krok 2: czekamy aż falownik się ustabilizuje
        _LOGGER.debug("Czekam %.2fs przed verify", verify_settling)
        await asyncio.sleep(verify_settling)

        # Krok 3: verify każdej komendy (tylko tych które się wykonały bez błędu)
        # i wyślij ACK z finalnym statusem
        for cmd, (executed_ok, exec_error) in zip(batch, execute_results):
            cmd_id = cmd["id"]

            if not executed_ok:
                # Komenda nie wykonała się — od razu ACK z błędem, bez verify
                await async_ack_command(
                    self.hass, self.coordinator_data, cmd_id, False, exec_error,
                )
                continue

            verify_ok, verify_error = self._verify_one(cmd)
            await async_ack_command(
                self.hass, self.coordinator_data, cmd_id, verify_ok, verify_error,
            )

    # === Pojedyncze operacje ===

    async def _execute_one(self, cmd: dict[str, Any]) -> tuple[bool, str | None]:
        """Wykonaj pojedynczą komendę przez hass.services.async_call.

        Zwraca ``(success, error_message)``. Brak wymaganych pól → od razu fail.
        """
        domain = cmd.get("domain")
        service = cmd.get("service")
        entity_id = cmd.get("entity_id")
        service_data = cmd.get("service_data") or {}

        if not domain or not service or not entity_id:
            return (False, "Invalid command: missing domain/service/entity_id")

        try:
            await self.hass.services.async_call(
                domain,
                service,
                {"entity_id": entity_id, **service_data},
                blocking=True,
            )
            _LOGGER.info("Wykonano komendę: %s.%s na %s", domain, service, entity_id)
            return (True, None)
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            _LOGGER.error(
                "Komenda nieudana (%s.%s na %s): %s",
                domain, service, entity_id, error_msg,
            )
            return (False, error_msg[:500])

    def _verify_one(self, cmd: dict[str, Any]) -> tuple[bool, str | None]:
        """Sprawdź czy encja ma wartość zgodną z tym co ustawialiśmy.

        Heurystyka po service name — patrz docstring modułu.
        Zwraca ``(success, error_message)``. Sukces = falownik faktycznie przyjął write.
        """
        service = cmd.get("service") or ""
        entity_id = cmd.get("entity_id") or ""
        service_data = cmd.get("service_data") or {}

        state_obj = self.hass.states.get(entity_id)
        if state_obj is None:
            return (False, f"Verify: encja {entity_id} nie istnieje w HA")

        actual = state_obj.state
        if actual in ("unknown", "unavailable"):
            return (False, f"Verify: encja {entity_id} ma stan {actual}")

        # number.set_value — porównujemy liczbę z tolerancją
        if service == "set_value":
            expected = service_data.get("value")
            if expected is None:
                _LOGGER.warning("Verify: brak pola 'value' w komendzie dla %s", entity_id)
                return (True, None)
            try:
                if abs(float(actual) - float(expected)) < 1.0:
                    return (True, None)
                return (False, f"Verify: oczekiwano {expected}, jest {actual}")
            except (ValueError, TypeError):
                return (False, f"Verify: niepoliczalne wartości expected={expected} actual={actual}")

        # select.select_option — porównujemy string
        if service == "select_option":
            expected = service_data.get("option")
            if expected is None:
                _LOGGER.warning("Verify: brak pola 'option' w komendzie dla %s", entity_id)
                return (True, None)
            if actual == expected:
                return (True, None)
            return (False, f"Verify: oczekiwano '{expected}', jest '{actual}'")

        # switch.turn_on / turn_off — porównujemy ze stałą "on"/"off"
        if service == "turn_on":
            return (True, None) if actual == "on" else (False, f"Verify: oczekiwano on, jest {actual}")
        if service == "turn_off":
            return (True, None) if actual == "off" else (False, f"Verify: oczekiwano off, jest {actual}")

        # Inne domeny — nie wiemy jak verify'ować, akceptujemy z warningiem
        _LOGGER.warning(
            "Verify: brak heurystyki dla service '%s' (entity %s) — akceptuję bez sprawdzenia",
            service, entity_id,
        )
        return (True, None)

    # === Odczyt konfiguracji z encji number ===

    def _get_command_delay(self) -> float:
        """Pobierz aktualną wartość command_delay z encji number (lub default)."""
        return float(self.coordinator_data.get("command_delay", DEFAULT_COMMAND_DELAY))

    def _get_verify_settling(self) -> float:
        """Pobierz aktualną wartość verify_settling z encji number (lub default)."""
        return float(self.coordinator_data.get("verify_settling", DEFAULT_VERIFY_SETTLING))
