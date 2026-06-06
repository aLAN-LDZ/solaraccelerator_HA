"""Platforma sensor — punkt wejścia HA dla wszystkich encji Solar Accelerator.

Tu HA wywołuje ``async_setup_entry``, który:
1. tworzy wszystkie encje sensorów z pakietu ``sensors/``,
2. startuje task pobrania cen i zysku zaraz po starcie (żeby UI nie świecił "unknown"),
3. uruchamia dwie pętle w tle (godzinową i live) z modułu ``coordinator``.

Klasy encji żyją w ``sensors/`` (pogrupowane po kategoriach), funkcje API w ``api.py``,
pętle w ``coordinator.py``. Ten plik celowo trzymamy cienki — sama lista co kiedy
rejestrujemy, bez logiki biznesowej.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import async_fetch_prices, async_fetch_profit
from .const import DOMAIN
from .coordinator import async_send_data_hourly, async_send_live_data_loop
from .sensors import (
    SolarAcceleratorAverageBuyPriceSensor,
    SolarAcceleratorAverageSellPriceSensor,
    SolarAcceleratorBatteryAvgPriceSensor,
    SolarAcceleratorBatteryValueSensor,
    SolarAcceleratorCurrentBuyPriceSensor,
    SolarAcceleratorCurrentSellPriceSensor,
    SolarAcceleratorDailyProfitSensor,
    SolarAcceleratorEntitiesCountSensor,
    SolarAcceleratorIsCheapSensor,
    SolarAcceleratorIsExpensiveSensor,
    SolarAcceleratorLastSentSensor,
    SolarAcceleratorLiveIntervalSensor,
    SolarAcceleratorLiveLastPushSensor,
    SolarAcceleratorLiveStatusSensor,
    SolarAcceleratorMaxBuyPriceSensor,
    SolarAcceleratorMaxSellPriceSensor,
    SolarAcceleratorMinBuyPriceSensor,
    SolarAcceleratorMinSellPriceSensor,
    SolarAcceleratorNextScheduledSensor,
    SolarAcceleratorPriceProviderSensor,
    SolarAcceleratorStatusSensor,
    SolarAcceleratorWriteStatsSensor,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Zarejestruj wszystkie sensory i uruchom pętle w tle."""

    coordinator_data = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([
        # Sensory diagnostyczne (status, znaczniki czasu, licznik encji)
        SolarAcceleratorStatusSensor(hass, entry, coordinator_data),
        SolarAcceleratorLastSentSensor(hass, entry, coordinator_data),
        SolarAcceleratorNextScheduledSensor(hass, entry, coordinator_data),
        SolarAcceleratorEntitiesCountSensor(hass, entry, coordinator_data),
        # Ceny zakupu energii
        SolarAcceleratorCurrentBuyPriceSensor(hass, entry, coordinator_data),
        SolarAcceleratorMinBuyPriceSensor(hass, entry, coordinator_data),
        SolarAcceleratorMaxBuyPriceSensor(hass, entry, coordinator_data),
        SolarAcceleratorAverageBuyPriceSensor(hass, entry, coordinator_data),
        # Ceny sprzedaży energii
        SolarAcceleratorCurrentSellPriceSensor(hass, entry, coordinator_data),
        SolarAcceleratorMinSellPriceSensor(hass, entry, coordinator_data),
        SolarAcceleratorMaxSellPriceSensor(hass, entry, coordinator_data),
        SolarAcceleratorAverageSellPriceSensor(hass, entry, coordinator_data),
        # Flagi i metadane cen
        SolarAcceleratorIsCheapSensor(hass, entry, coordinator_data),
        SolarAcceleratorIsExpensiveSensor(hass, entry, coordinator_data),
        SolarAcceleratorPriceProviderSensor(hass, entry, coordinator_data),
        # Sensory zysku i wyceny baterii
        SolarAcceleratorDailyProfitSensor(hass, entry, coordinator_data),
        SolarAcceleratorBatteryValueSensor(hass, entry, coordinator_data),
        SolarAcceleratorBatteryAvgPriceSensor(hass, entry, coordinator_data),
        # Sensory kanału live (status, ostatni push, interwał)
        SolarAcceleratorLiveStatusSensor(hass, entry, coordinator_data),
        SolarAcceleratorLiveLastPushSensor(hass, entry, coordinator_data),
        SolarAcceleratorLiveIntervalSensor(hass, entry, coordinator_data),
        # Diagnostyka write_managera — retry/status per sterowana encja
        SolarAcceleratorWriteStatsSensor(hass, entry, coordinator_data),
    ])

    # Pobierz ceny i zysk od razu na starcie — żeby sensory nie świeciły "unknown"
    # przed pierwszą pełną godziną. Background — żeby wolny serwer nie blokował bootstrap.
    entry.async_create_background_task(
        hass, async_fetch_prices(hass, coordinator_data), "sa_fetch_prices_init"
    )
    entry.async_create_background_task(
        hass, async_fetch_profit(hass, coordinator_data), "sa_fetch_profit_init"
    )

    # Pętla godzinowa — pełna paczka danych co pełną godzinę.
    # background_task = HA nie czeka na nią podczas bootstrap (to nieskończony while True).
    entry.async_create_background_task(
        hass,
        async_send_data_hourly(hass, entry, coordinator_data),
        "sa_send_data_hourly",
    )

    # Pętla live — szybki push stanu i odbiór komend co kilkanaście sekund
    entry.async_create_background_task(
        hass,
        async_send_live_data_loop(hass, entry, coordinator_data),
        "sa_send_live_data_loop",
    )
