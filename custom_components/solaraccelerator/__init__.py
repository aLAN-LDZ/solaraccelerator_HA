"""Integracja Solar Accelerator dla Home Assistant.

Punkt wejścia całej integracji — HA wywołuje:
- ``async_setup_entry``  przy dodaniu wpisu konfiguracji albo restarcie HA,
- ``async_unload_entry`` przy usunięciu wpisu lub reloadzie integracji.

W ``async_setup_entry`` inicjalizujemy współdzielony słownik
``hass.data[DOMAIN][entry.entry_id]`` (tzw. coordinator_data). Wszystkie inne
moduły (sensory, api, coordinator, button) czytają i zapisują do tego słownika.

UWAGA: docelowo to powinno trafić do osobnej klasy ``Coordinator`` (Etap 1+ refaktoru).
Na razie zostaje jako słownik z czytelnymi kluczami.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_SERVER_URL,
    CONF_ENTITY_MAPPING,
    CONF_SOLARMAN_PREFIX,
    CONF_EV_ENABLED,
    CONF_EV_PREFIX,
    DEFAULT_LIVE_INTERVAL,
)

LOGGER = logging.getLogger(__name__)

# Platformy HA które ładuje ta integracja (każda ma swój plik async_setup_entry)
PLATFORMS = ["sensor", "button"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Załaduj integrację z wpisu konfiguracji.

    Inicjalizujemy słownik z całym stanem run-time — wartości z config flow
    oraz bufory na dane pobierane z backendu (ceny, zysk, status live).
    Sensory podlinkują się do tego słownika i będą z niego czytać.
    """

    hass.data.setdefault(DOMAIN, {})

    hass.data[DOMAIN][entry.entry_id] = {
        # Dane z config flow
        CONF_API_KEY: entry.data.get(CONF_API_KEY),
        CONF_SERVER_URL: entry.data.get(CONF_SERVER_URL),
        CONF_ENTITY_MAPPING: entry.data.get(CONF_ENTITY_MAPPING, {}),
        CONF_SOLARMAN_PREFIX: entry.data.get(CONF_SOLARMAN_PREFIX, ""),
        CONF_EV_ENABLED: entry.data.get(CONF_EV_ENABLED, False),
        CONF_EV_PREFIX: entry.data.get(CONF_EV_PREFIX, ""),
        # Stan pętli godzinowej
        "last_sent": None,
        "next_scheduled": None,
        "last_response": None,
        "connection_status": "unknown",
        "entities_sent": 0,
        # Stan kanału live (szybki push)
        "live_status": "inactive",
        "live_last_push": None,
        "live_interval_seconds": DEFAULT_LIVE_INTERVAL,
        # Bufor cen energii — uzupełnia async_fetch_prices, czytają sensory cen
        "prices": {
            "current_price": None,
            "min_price": None,
            "max_price": None,
            "average_price": None,
            "is_cheap": None,
            "is_expensive": None,
            "provider": None,
            "updated_at": None,
        },
        "prices_last_update": None,
        # Bufor zysku dziennego — uzupełnia async_fetch_profit po data-ready
        "profit": {
            "date": None,
            "daily_profit_pln": None,
            "daily_load_cost_pln": None,
            "daily_import_cost_pln": None,
            "daily_export_value_pln": None,
            "daily_battery_delta_pln": None,
            "hourly_count": None,
            "currency": None,
            "updated_at": None,
        },
        "profit_last_update": None,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Wyładuj integrację — anuluj taski w tle i odepnij platformy."""
    coordinator_data = hass.data[DOMAIN].get(entry.entry_id, {})

    # Anuluj obie pętle w tle — inaczej zostałyby "wiszące" po reloadzie
    if task := coordinator_data.get("_task"):
        task.cancel()
    if live_task := coordinator_data.get("_live_task"):
        live_task.cancel()

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
