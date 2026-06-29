"""Kanoniczny kontrakt sterowania — wspólny słownik pojęć dla wszystkich falowników.

Trzy grupy:

- ``ACTIONS``              — intencje optymalizatora (co ma się dziać w danej godzinie).
                            Niezależne od sprzętu; profil tłumaczy je później na konkretne
                            komendy swojego falownika.
- ``CAPABILITIES``         — „pole działania": co dany falownik w ogóle potrafi. Profil to
                            deklaruje, dzięki czemu nie próbujemy wykonać akcji, której
                            urządzenie nie obsługuje.
- ``CONTROL_CAPABILITIES`` — kanoniczne „pokrętła" sterujące (encje, którymi steruje się
                            falownikiem). Użytkownik mapuje je na swoje encje HA, tak samo
                            jak encje odczytu. Część pól może zostać niezmapowana, jeśli
                            dany falownik ich nie ma.

Ten plik jest źródłem prawdy po stronie integracji. Wartości typu (``value_type``)
decydują, jaką encję pokazać w mapowaniu i jak ją przetestować/ustawić lokalnie.
"""
from __future__ import annotations

# === Akcje (intencje) — co ma robić falownik w danej godzinie ===
# Wartości muszą pozostać stabilne (są częścią kontraktu z serwisem).
ACTIONS: list[str] = [
    "idle_day",
    "idle_night",
    "charge_pv",
    "charge_grid",
    "discharge_load",
    "discharge_grid",
    "full_power_grid",
]

# === Capabilities — co falownik potrafi (pole działania) ===
# Format: (key, label). Profil deklaruje wartości bool; brak = False.
CAPABILITIES: list[tuple[str, str]] = [
    ("grid_charge", "Falownik potrafi ładować baterię z sieci"),
    ("export", "Falownik potrafi eksportować energię do sieci"),
    ("soc_control", "Falownik pozwala ustawić docelowy SOC baterii"),
    ("mixed_charging", "Falownik potrafi ładować jednocześnie z PV i z sieci"),
]
CAPABILITY_KEYS: list[str] = [c[0] for c in CAPABILITIES]


# === Typy wartości encji sterujących ===
# Każdy typ mapuje się na: domeny encji pokazywane w selektorze + usługę HA użytą
# do ustawienia/testu wartości.
VALUE_TYPE_DOMAINS: dict[str, list[str]] = {
    "number": ["number", "input_number"],
    "select": ["select", "input_select"],
    "switch": ["switch", "input_boolean"],
    "time": ["time", "input_datetime"],
}


def _tou_slots(count: int) -> list[tuple[str, str, str, str]]:
    """Zbuduj wpisy harmonogramu TOU dla ``count`` slotów (start + SOC + tryb ładowania)."""
    out: list[tuple[str, str, str, str]] = []
    for n in range(1, count + 1):
        out.append((f"tou_{n}_time", f"Slot {n}: godzina startu (time)", "time", "schedule"))
        out.append((f"tou_{n}_soc", f"Slot {n}: docelowy SOC [%] (number)", "number", "schedule"))
        out.append((f"tou_{n}_charge_mode", f"Slot {n}: tryb ładowania (select)", "select", "schedule"))
    return out


# === Kanoniczne encje sterujące ===
# Format: (key, label, value_type, category).
# Globalne „pokrętła" + harmonogram TOU (6 slotów). Falownik, który czegoś nie ma,
# zostawia dane pole niezmapowane.
CONTROL_CAPABILITIES: list[tuple[str, str, str, str]] = [
    # Globalne ustawienia pracy. Etykiety zawierają typ encji i jednostkę, żeby nie było
    # wątpliwości (np. peak shaving to przełącznik on/off, nie wartość mocy).
    ("work_mode", "Tryb pracy falownika (select)", "select", "inverter"),
    ("battery_max_charge_current", "Maks. prąd ładowania baterii [A] (number)", "number", "battery"),
    ("battery_max_discharge_current", "Maks. prąd rozładowania baterii [A] (number)", "number", "battery"),
    ("grid_peak_shaving", "Peak shaving z sieci — włącznik on/off (switch)", "switch", "grid"),
    ("pv_power_limit", "Limit mocy PV [W] (number)", "number", "pv"),
] + _tou_slots(6)

CONTROL_KEYS: list[str] = [c[0] for c in CONTROL_CAPABILITIES]

# Czytelne nazwy kategorii sterowania (grupowanie w kreatorze).
CONTROL_CATEGORIES: dict[str, str] = {
    "inverter": "Tryb pracy inwertera",
    "battery": "Sterowanie baterią",
    "grid": "Sterowanie siecią",
    "pv": "Sterowanie PV",
    "schedule": "Harmonogram (TOU)",
}


def control_value_type(control_key: str) -> str | None:
    """Zwróć typ wartości encji sterującej (``number``/``select``/``switch``/``time``)."""
    for key, _label, value_type, _category in CONTROL_CAPABILITIES:
        if key == control_key:
            return value_type
    return None


def control_entity_domains(control_key: str) -> list[str]:
    """Zwróć domeny encji dopuszczone dla danej encji sterującej (do selektora HA)."""
    value_type = control_value_type(control_key)
    return VALUE_TYPE_DOMAINS.get(value_type, []) if value_type else []


def controls_for_category(category: str) -> list[tuple[str, str, str, str]]:
    """Zwróć encje sterujące należące do danej kategorii."""
    return [c for c in CONTROL_CAPABILITIES if c[3] == category]
