"""Zdrowie łącza falownik ↔ Home Assistant — detekcja utraty komunikacji.

Problem
-------
Gdy falownik traci łączność (Modbus/Solarman przestaje go odpytywać), encje w HA
przechodzą w stan ``unavailable``. ``convert_value`` (helpers.py) spłaszcza je do
``0`` — backend dostaje komplet zer, które psują wykresy i statystyki. Zera bywają
normalne (np. moc PV w nocy), ale NIE na wszystkich encjach naraz.

Jak wykrywamy offline — "parametry życiowe"
-------------------------------------------
Opieramy się na encjach, które są niezerowe ZAWSZE gdy falownik żyje — nawet w
nocy przy zerowym przepływie mocy: napięcie baterii (~50V), napięcie sieci (~230V),
częstotliwość (~50Hz). Falownik uznajemy za:
- ``online``  — co najmniej jeden "vital" ma sensowną wartość ≠ 0,
- ``offline`` — wszystkie vitale są naraz ``unavailable``/``unknown``/``0``.

Gdy żaden vital nie jest zmapowany, nie umiemy ocenić → zakładamy ``online``
(nie psujemy dotychczasowego zachowania).

Debounce + arming
-----------------
Status przełączamy dopiero po ``DEBOUNCE_CYCLES`` kolejnych spójnych odczytach
(migotanie Modbusu resetuje licznik) — żeby nie wysyłać na iOS "stracił/odzyskał"
przy każdym mignięciu. Dodatkowo detektor "uzbraja się" dopiero po pierwszym
odczycie ``online``: zanim raz zobaczymy żywy falownik (np. tuż po starcie HA gdy
Solarman jeszcze się ładuje), NIE zgłaszamy offline.

Stan trzymamy w ``coordinator_data``; ``update_inverter_health`` wołamy z pętli
live (stała kadencja ~kilkanaście s definiuje rytm debounce).
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import CONF_ENTITY_MAPPING

_LOGGER = logging.getLogger(__name__)

# Encje "życiowe" — niezerowe zawsze gdy falownik ma komunikację (fizyka, nie moc)
VITAL_ENTITY_KEYS = ("battery_voltage", "inverter_voltage_l1", "load_frequency")

# Ile kolejnych spójnych odczytów musi paść, zanim przełączymy zadeklarowany status
DEBOUNCE_CYCLES = 2

UNAVAILABLE_STATES = ("unknown", "unavailable")


def _vital_alive(hass: HomeAssistant, entity_id: str | None) -> bool | None:
    """Czy pojedynczy vital żyje: ``True`` (≠0), ``False`` (martwy), ``None`` (brak encji)."""
    if not entity_id:
        return None
    state_obj = hass.states.get(entity_id)
    if state_obj is None:
        return None
    if state_obj.state in UNAVAILABLE_STATES:
        return False
    try:
        return abs(float(state_obj.state)) > 0.0
    except (ValueError, TypeError):
        return False


def _evaluate_raw(hass: HomeAssistant, coordinator_data: dict[str, Any]) -> bool:
    """Surowy (bez debounce) odczyt: czy falownik wygląda na online wg vitali."""
    mapping = coordinator_data.get(CONF_ENTITY_MAPPING, {})
    readings = [_vital_alive(hass, mapping.get(k)) for k in VITAL_ENTITY_KEYS]
    present = [r for r in readings if r is not None]
    if not present:
        return True  # vitale niezmapowane — nie umiemy ocenić, zakładamy online
    return any(present)  # co najmniej jeden vital żyje → online


def update_inverter_health(hass: HomeAssistant, coordinator_data: dict[str, Any]) -> bool:
    """Zaktualizuj zadeklarowany status komunikacji falownika (z debounce + arming).

    Zwraca aktualny zadeklarowany status (``True`` = online). Zapisuje go w
    ``coordinator_data["inverter_online"]`` i — przy przełączeniu — woła
    ``inverter_health_notify`` (odświeża binary_sensor natychmiast).
    """
    raw = _evaluate_raw(hass, coordinator_data)

    # Licznik kolejnych identycznych surowych odczytów (migotanie resetuje)
    if raw == coordinator_data.get("_inverter_raw_last"):
        streak = coordinator_data.get("_inverter_raw_streak", 0) + 1
    else:
        streak = 1
    coordinator_data["_inverter_raw_last"] = raw
    coordinator_data["_inverter_raw_streak"] = streak

    # Uzbrojenie: dopiero pierwszy odczyt online pozwala później zgłaszać offline
    if raw:
        coordinator_data["_inverter_health_armed"] = True

    declared = coordinator_data.get("inverter_online", True)
    if raw != declared and streak >= DEBOUNCE_CYCLES:
        # Nie zgłaszaj offline zanim choć raz zobaczyliśmy żywy falownik
        if not raw and not coordinator_data.get("_inverter_health_armed"):
            return declared
        coordinator_data["inverter_online"] = raw
        declared = raw
        _LOGGER.warning(
            "Komunikacja z falownikiem: %s", "ODZYSKANA" if raw else "UTRACONA"
        )
        if (notify := coordinator_data.get("inverter_health_notify")):
            try:
                notify()
            except Exception as e:  # noqa: BLE001
                _LOGGER.debug("inverter_health notifier rzucił wyjątek: %s", e)

    return declared
