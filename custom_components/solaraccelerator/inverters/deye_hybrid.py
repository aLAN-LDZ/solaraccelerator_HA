"""Kanoniczny model sterowania: falowniki hybrydowe Deye (rodzina SUN-*-SG0*).

Definiuje kanoniczne wartości enumów i knoby, na które celuje optymalizator. Źródła
(Solarman, SolarAssistant, …) mapują je na swoje encje w plikach profili. Wartości
liczbowe i czasowe są kanoniczne (czas = minuty od północy, prądy = A, SOC = %).
"""
from __future__ import annotations

MODEL_ID = "deye_hybrid"

# Kanoniczne tryby pracy (źródła mapują je na swoje etykiety selecta przez kodek ``enum``).
WORK_MODE_VALUES: tuple[str, ...] = ("export_first", "zero_export_to_load")

# Kanoniczne źródło ładowania w slocie TOU (źródła: 1 select albo fan-out na switche).
CHARGE_SOURCE_VALUES: tuple[str, ...] = ("off", "grid", "gen", "both")

# Liczba slotów harmonogramu TOU.
TOU_SLOTS = 6

# Knoby modelu i ich kanoniczny typ wartości (do walidacji bindingów i UI harvestu).
# value_type: number | time | enum | bool
CONTROL_MODEL: dict[str, str] = {
    "work_mode": "enum",
    "battery_max_charge_current": "number",
    "battery_max_discharge_current": "number",
    "pv_power_limit": "number",
    "grid_peak_shaving": "bool",
    **{f"tou_{n}_time": "time" for n in range(1, TOU_SLOTS + 1)},
    **{f"tou_{n}_soc": "number" for n in range(1, TOU_SLOTS + 1)},
    **{f"tou_{n}_charge_mode": "enum" for n in range(1, TOU_SLOTS + 1)},
}


def canonical_type(knob: str) -> str | None:
    """Kanoniczny typ wartości knoba (``number``/``time``/``enum``/``bool``) lub ``None``."""
    return CONTROL_MODEL.get(knob)


def canonical_values(knob: str) -> tuple[str, ...] | None:
    """Kanoniczny zbiór wartości dla knobów enum (work_mode, tou_*_charge_mode)."""
    if knob == "work_mode":
        return WORK_MODE_VALUES
    if knob.endswith("_charge_mode"):
        return CHARGE_SOURCE_VALUES
    return None
