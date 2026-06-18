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
from homeassistant.loader import async_get_integration

from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_SERVER_URL,
    CONF_ENTITY_MAPPING,
    CONF_SOLARMAN_PREFIX,
    CONF_EV_ENABLED,
    CONF_EV_PREFIX,
    CONF_CONTROLLABLE_DEVICES,
    DATA_GUARD_ENABLED,
    DEFAULT_COMMAND_DELAY,
    DEFAULT_GUARD_ENABLED,
    DEFAULT_LIVE_INTERVAL,
    DEFAULT_SERVER_URL,
    DEFAULT_VERIFY_SETTLING,
)
from .frontend import async_register_chart_view, async_setup_card
from .guard import SettingsGuard
from .write_manager import WriteManager

LOGGER = logging.getLogger(__name__)

# Platformy HA które ładuje ta integracja (każda ma swój plik async_setup_entry)
PLATFORMS = ["sensor", "binary_sensor", "button", "number", "switch"]


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
        # Custom sterowalne odbiorniki z OptionsFlow (entry.options, edytowalne bez
        # ponownego dodawania integracji). Dosyłane w payloadzie jako controllable_devices.
        CONF_CONTROLLABLE_DEVICES: entry.options.get(CONF_CONTROLLABLE_DEVICES, []),
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
        # Status komunikacji falownik↔HA — aktualizowany przez health.update_inverter_health
        # w pętli live (vitale + debounce). Domyślnie online, dopóki nie wykryjemy utraty.
        "inverter_online": True,
        "inverter_health_notify": None,
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
        # Wartości encji konfiguracyjnych write_managera — nadpisywane przez encje number
        # przy starcie (z RestoreEntity) i przy każdej zmianie z UI.
        "command_delay": DEFAULT_COMMAND_DELAY,
        "verify_settling": DEFAULT_VERIFY_SETTLING,
        # Przełącznik "Pilnuj ustawień" — nadpisywany przez encję switch (RestoreEntity).
        DATA_GUARD_ENABLED: DEFAULT_GUARD_ENABLED,
        # Diagnostyka write_managera — kumulatywne statystyki per entity_id (retry, ok/fail)
        # i meta ostatniego batcha. Aktualizowane w WriteManager._process_batch.
        "write_stats": {
            "entities": {},      # entity_id → {total_commands, total_retries, last_retries, last_status, last_error, last_value, last_attempt_at}
            "last_batch_at": None,
            "last_batch_size": 0,
            "last_batch_acked": 0,
            "last_batch_failed": 0,
            "last_batch_retried": 0,  # liczba komend które wymagały >=1 retry
        },
    }

    # WriteManager — kolejka komend do falownika z worker'em w tle.
    # Tworzymy przed forward_entry_setups, żeby platformy mogły do niej trafić przez coordinator_data.
    write_manager = WriteManager(hass, entry, hass.data[DOMAIN][entry.entry_id])
    hass.data[DOMAIN][entry.entry_id]["write_manager"] = write_manager
    write_manager.start()

    # SettingsGuard — "pilnuj ustawień": po komendzie zapamiętuje docelowy stan encji
    # i przywraca go gdy falownik sam ucieknie. Sweep startuje od razu, subskrypcja
    # zdarzeń tworzy się leniwie przy pierwszej zarejestrowanej encji.
    settings_guard = SettingsGuard(hass, hass.data[DOMAIN][entry.entry_id])
    hass.data[DOMAIN][entry.entry_id]["settings_guard"] = settings_guard
    settings_guard.start()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Karty Lovelace: proxy danych (server-side, dokłada klucz API z konfiguracji)
    # + bundel karty pobierany z backendu i serwowany LOKALNIE z HA (działa nawet
    # gdy sieć przeglądarki blokuje domenę backendu). Idempotentne.
    async_register_chart_view(hass)
    server_url = entry.data.get(CONF_SERVER_URL) or DEFAULT_SERVER_URL
    integration = await async_get_integration(hass, DOMAIN)
    await async_setup_card(hass, server_url, integration.version)

    # Reload integracji po zmianie opcji (OptionsFlow) — żeby nowa lista
    # sterowalnych encji trafiła do coordinator_data bez ręcznego restartu.
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Przeładuj wpis po zapisaniu opcji (dodanie/usunięcie udostępnianych encji)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Wyładuj integrację — zatrzymaj write_manager i odepnij platformy.

    Pętle godzinowa/live są tworzone przez ``entry.async_create_background_task`` —
    HA anuluje je automatycznie przy unload. WriteManager tworzy własny task przez
    ``hass.async_create_background_task`` więc go zatrzymujemy ręcznie.
    """
    coordinator_data = hass.data[DOMAIN].get(entry.entry_id, {})

    # Zatrzymaj worker'a write_managera (osobny task niezwiązany z entry)
    if write_manager := coordinator_data.get("write_manager"):
        write_manager.stop()

    # Odepnij nasłuchy guarda (sweep + state_changed) — też niezwiązane z entry
    if settings_guard := coordinator_data.get("settings_guard"):
        settings_guard.stop()

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
