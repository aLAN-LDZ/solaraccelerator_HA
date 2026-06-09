"""Funkcje pomocnicze używane w wielu miejscach integracji."""
from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util


def convert_value(value: str | None, entity_key: str) -> float | int | bool | str | None:
    """Zamień wartość encji HA na typ akceptowany przez backend.

    HA przechowuje stany jako stringi, a backend oczekuje konkretnych typów:
    - tekstowe pola (status ładowarki, status falownika, błędy) zostają stringiem,
    - grid_connected_status zamieniamy na bool,
    - resztę próbujemy sparsować jako liczbę (int gdy całkowita, float zaokrąglony do 2 miejsc).

    Gdy stan jest None, ``unknown``, ``unavailable`` lub pusty — zwracamy 0,
    żeby backend dostał spójny payload zamiast pustych pól.
    """
    if value is None or value in ("unknown", "unavailable", ""):
        return 0

    if entity_key == "grid_connected_status":
        return value.lower() in ("on", "true", "1", "connected")

    if entity_key == "inverter_status":
        return value

    # Encje ładowarki EV (OCPP) mają wartości tekstowe — nie próbuj ich parsować jako liczby
    if entity_key in ("status", "status_connector", "vendor", "error_code", "transaction_id"):
        return value

    try:
        float_val = float(value)
        if float_val.is_integer():
            return int(float_val)
        return round(float_val, 2)
    except (ValueError, TypeError):
        # Wartość nie jest liczbą — zwracamy 0 zamiast wywalać błąd na backend
        return 0


def get_next_full_hour() -> datetime:
    """Zwróć timestamp najbliższej pełnej godziny (np. teraz 14:37 → 15:00:00)."""
    now = dt_util.now()
    next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return next_hour


def get_seconds_until_next_hour() -> float:
    """Zwróć liczbę sekund pozostałych do najbliższej pełnej godziny."""
    now = dt_util.now()
    next_hour = get_next_full_hour()
    return (next_hour - now).total_seconds()


def state_matches_expected(
    service: str,
    service_data: dict,
    actual: str,
) -> tuple[bool, str | None]:
    """Czy bieżący stan encji (``actual``) odpowiada temu, co ustawialiśmy komendą.

    Jedno źródło prawdy dla dwóch mechanizmów:
    - ``write_manager`` po wysłaniu komendy weryfikuje czy falownik ją przyjął,
    - ``guard`` ("pilnuj ustawień") sprawdza czy falownik nie odszedł od planu.

    Heurystyka po nazwie ``service`` (HA trzyma stany jako stringi):
    - ``set_value``     — liczba z tolerancją 1.0 (encja number),
    - ``select_option`` — dokładny string,
    - ``turn_on``/``turn_off`` — stan ``on``/``off``,
    - inne / brak pola w ``service_data`` — akceptujemy (brak heurystyki, np.
      ``time.set_value`` używa klucza ``time`` a nie ``value``).

    Stan ``unknown``/``unavailable`` zawsze traktujemy jako niezgodny.

    Zwraca ``(zgodne, powod)`` — ``powod`` jest ``None`` gdy zgodne, a w przeciwnym
    razie krótkim opisem rozbieżności (do logów / komunikatu verify).
    """
    if actual in ("unknown", "unavailable"):
        return (False, f"stan {actual}")

    if service == "set_value":
        expected = service_data.get("value")
        if expected is None:
            return (True, None)
        try:
            if abs(float(actual) - float(expected)) < 1.0:
                return (True, None)
            return (False, f"oczekiwano {expected}, jest {actual}")
        except (ValueError, TypeError):
            return (False, f"niepoliczalne expected={expected} actual={actual}")

    if service == "select_option":
        expected = service_data.get("option")
        if expected is None:
            return (True, None)
        if actual == expected:
            return (True, None)
        return (False, f"oczekiwano '{expected}', jest '{actual}'")

    if service == "turn_on":
        return (True, None) if actual == "on" else (False, f"oczekiwano on, jest {actual}")
    if service == "turn_off":
        return (True, None) if actual == "off" else (False, f"oczekiwano off, jest {actual}")

    # Nieznany service — nie wiemy jak porównać, akceptujemy
    return (True, None)
