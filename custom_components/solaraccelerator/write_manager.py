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
from datetime import datetime, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import async_ack_command
from .const import (
    DEFAULT_COMMAND_DELAY,
    DEFAULT_VERIFY_RETRIES,
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
        """Uruchom worker'a w tle. Bezpieczne do wielokrotnego wywołania.

        ``async_create_background_task`` zamiast ``async_create_task`` — worker to
        nieskończona pętla, której HA nigdy nie powinien oczekiwać podczas bootstrap.
        """
        if self._worker_task and not self._worker_task.done():
            return
        self._worker_task = self.hass.async_create_background_task(
            self._worker(), "sa_write_manager_worker"
        )

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
        """Wykonaj jedną batch komend: execute → settle → verify → (retry × N) → ACK.

        Retry verify
        ------------
        Po pierwszym verify zbieramy komendy które wykonały się bez wyjątku ale
        nie przeszły verify (np. Modbus odrzucił write — falownik nie zmienił
        wartości w rejestrze). Robimy dla nich do ``verify_retries`` dodatkowych
        rund: execute_failed → settle → verify. Każda runda redukuje listę
        do-retry o te które już przeszły. Po wyczerpaniu prób ACK z ostatnim
        verify_error.

        Komendy które rzuciły wyjątkiem w ``_execute_one`` (encja unavailable,
        timeout HA itp.) NIE są retry'owane — to znak że problem jest "wyżej"
        niż pojedynczy write i ponowienie nic nie da.
        """
        command_delay = self._get_command_delay()
        verify_settling = self._get_verify_settling()
        verify_retries = self._get_verify_retries()

        _LOGGER.info(
            "Przetwarzam batch %d komend (delay=%.2fs, settling=%.2fs, retries=%d)",
            len(batch), command_delay, verify_settling, verify_retries,
        )

        # Licznik prób per indeks komendy w batchu — 0 = tylko pierwsza próba przeszła
        # (bez retry), 1 = jeden retry, ... Używany do diagnostyki (sensor write_stats).
        retry_counts: list[int] = [0] * len(batch)

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

        # Krok 3: pierwsza runda verify
        # Trzymamy stan per-komenda: (verify_ok, error_message)
        # Komendy z exec_error mają od razu verify_ok=False i nie są retry'owane.
        verify_results: list[tuple[bool, str | None]] = []
        for cmd, (executed_ok, exec_error) in zip(batch, execute_results):
            if not executed_ok:
                verify_results.append((False, exec_error))
            else:
                verify_results.append(self._verify_one(cmd))

        # Krok 4: retry verify dla komend które wykonały się ale verify failed
        for attempt in range(1, verify_retries + 1):
            to_retry_idx = [
                i for i in range(len(batch))
                if execute_results[i][0] and not verify_results[i][0]
            ]
            if not to_retry_idx:
                break

            _LOGGER.warning(
                "Verify retry %d/%d dla %d komend: %s",
                attempt, verify_retries, len(to_retry_idx),
                [batch[i].get("entity_id") for i in to_retry_idx],
            )

            # Każda komenda którą próbujemy w tej rundzie dostaje +1 do licznika
            for idx in to_retry_idx:
                retry_counts[idx] = attempt

            # ponów execute dla każdej z command_delay między
            for j, idx in enumerate(to_retry_idx):
                success, error = await self._execute_one(batch[idx])
                if not success:
                    # exec wywalił się w retry — zapisujemy fail i wyłączamy z dalszego verify
                    execute_results[idx] = (False, error)
                    verify_results[idx] = (False, error)
                if j < len(to_retry_idx) - 1:
                    await asyncio.sleep(command_delay)

            # settle i ponowny verify tylko dla tych których exec się powiódł
            await asyncio.sleep(verify_settling)
            for idx in to_retry_idx:
                if execute_results[idx][0]:
                    verify_results[idx] = self._verify_one(batch[idx])
                    if verify_results[idx][0]:
                        _LOGGER.info(
                            "Verify OK na próbie %d/%d dla %s",
                            attempt + 1, verify_retries + 1,
                            batch[idx].get("entity_id"),
                        )

        # Krok 5: zaktualizuj statystyki diagnostyczne i wyślij ACK
        self._update_write_stats(batch, verify_results, retry_counts)

        for cmd, (verify_ok, verify_error) in zip(batch, verify_results):
            await async_ack_command(
                self.hass, self.coordinator_data, cmd["id"], verify_ok, verify_error,
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

    def _get_verify_retries(self) -> int:
        """Pobierz aktualną liczbę dodatkowych prób verify (0 = brak retry)."""
        return int(self.coordinator_data.get("verify_retries", DEFAULT_VERIFY_RETRIES))

    # === Diagnostyka (zasilanie sensora write_stats) ===

    def _update_write_stats(
        self,
        batch: list[dict[str, Any]],
        verify_results: list[tuple[bool, str | None]],
        retry_counts: list[int],
    ) -> None:
        """Zaktualizuj kumulatywne statystyki per-entity i meta ostatniego batcha.

        Wynik trafia do ``coordinator_data['write_stats']``, skąd czyta go
        ``SolarAcceleratorWriteStatsSensor``. Per-entity statystyki są kumulatywne
        (od startu integracji), meta odnosi się tylko do ostatnio przetworzonego batcha.
        """
        stats = self.coordinator_data.get("write_stats")
        if not stats:
            return

        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        entities_map: dict[str, dict[str, Any]] = stats.setdefault("entities", {})

        batch_acked = 0
        batch_failed = 0
        batch_retried = 0

        for cmd, (verify_ok, verify_error), retries in zip(batch, verify_results, retry_counts):
            entity_id = cmd.get("entity_id") or "unknown"
            service_data = cmd.get("service_data") or {}
            # Wyciągnij wartość żądaną — różny klucz zależnie od service
            requested_value = (
                service_data.get("value")
                or service_data.get("option")
                or service_data.get("time")
            )

            entry_stats = entities_map.setdefault(entity_id, {
                "total_commands": 0,
                "total_retries": 0,
                "last_retries": 0,
                "last_status": None,
                "last_error": None,
                "last_value": None,
                "last_attempt_at": None,
            })

            entry_stats["total_commands"] += 1
            entry_stats["total_retries"] += retries
            entry_stats["last_retries"] = retries
            entry_stats["last_status"] = "ok" if verify_ok else "failed"
            entry_stats["last_error"] = None if verify_ok else verify_error
            entry_stats["last_value"] = requested_value
            entry_stats["last_attempt_at"] = now_iso

            if verify_ok:
                batch_acked += 1
            else:
                batch_failed += 1
            if retries > 0:
                batch_retried += 1

        stats["last_batch_at"] = now_iso
        stats["last_batch_size"] = len(batch)
        stats["last_batch_acked"] = batch_acked
        stats["last_batch_failed"] = batch_failed
        stats["last_batch_retried"] = batch_retried

        # Push stanu do sensora — jeśli jest podpięty, odświeży się natychmiast
        if (notifier := self.coordinator_data.get("write_stats_notify")):
            try:
                notifier()
            except Exception as e:  # noqa: BLE001
                _LOGGER.debug("write_stats notifier rzucił wyjątek: %s", e)
