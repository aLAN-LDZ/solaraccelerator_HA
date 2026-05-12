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
