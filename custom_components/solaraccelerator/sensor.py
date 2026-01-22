"""Sensor platform for Solar Accelerator integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_SERVER_URL,
    CONF_ENTITY_MAPPING,
    CONF_SOLARMAN_PREFIX,
    API_SEND_DATA_ENDPOINT,
    API_PRICES_ENDPOINT,
    API_PROFIT_ENDPOINT,
    ENTITY_KEYS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor platform."""

    coordinator_data = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([
        SolarAcceleratorStatusSensor(hass, entry, coordinator_data),
        SolarAcceleratorLastSentSensor(hass, entry, coordinator_data),
        SolarAcceleratorNextScheduledSensor(hass, entry, coordinator_data),
        SolarAcceleratorEntitiesCountSensor(hass, entry, coordinator_data),
        # Buy price sensors
        SolarAcceleratorCurrentBuyPriceSensor(hass, entry, coordinator_data),
        SolarAcceleratorMinBuyPriceSensor(hass, entry, coordinator_data),
        SolarAcceleratorMaxBuyPriceSensor(hass, entry, coordinator_data),
        SolarAcceleratorAverageBuyPriceSensor(hass, entry, coordinator_data),
        # Sell price sensors
        SolarAcceleratorCurrentSellPriceSensor(hass, entry, coordinator_data),
        SolarAcceleratorMinSellPriceSensor(hass, entry, coordinator_data),
        SolarAcceleratorMaxSellPriceSensor(hass, entry, coordinator_data),
        SolarAcceleratorAverageSellPriceSensor(hass, entry, coordinator_data),
        # Price metadata sensors
        SolarAcceleratorIsCheapSensor(hass, entry, coordinator_data),
        SolarAcceleratorIsExpensiveSensor(hass, entry, coordinator_data),
        SolarAcceleratorPriceProviderSensor(hass, entry, coordinator_data),
        # Profit sensors
        SolarAcceleratorDailyProfitSensor(hass, entry, coordinator_data),
        SolarAcceleratorBatteryValueSensor(hass, entry, coordinator_data),
        SolarAcceleratorBatteryAvgPriceSensor(hass, entry, coordinator_data),
    ])

    # Fetch prices and profit immediately on startup
    hass.async_create_task(async_fetch_prices(hass, coordinator_data))
    hass.async_create_task(async_fetch_profit(hass, coordinator_data))

    # Start hourly data sending task
    task = hass.async_create_task(
        async_send_data_hourly(hass, entry, coordinator_data)
    )
    coordinator_data["_task"] = task


class SolarAcceleratorSensorBase(SensorEntity):
    """Base class for Solar Accelerator sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator_data: dict[str, Any],
        sensor_type: str,
    ) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self.entry = entry
        self.coordinator_data = coordinator_data
        self.sensor_type = sensor_type
        self._attr_unique_id = f"{entry.entry_id}_{sensor_type}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name="SolarAccelerator",
            manufacturer="SolarAccelerator",
            model="Home Assistant Integration",
            entry_type=DeviceEntryType.SERVICE,
        )


class SolarAcceleratorStatusSensor(SolarAcceleratorSensorBase):
    """Sensor for connection status."""

    _attr_icon = "mdi:cloud-check"
    _attr_translation_key = "connection_status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Initialize."""
        super().__init__(hass, entry, coordinator_data, "connection_status")
        self._attr_name = "Status połączenia"

    @property
    def native_value(self) -> str:
        """Return the state."""
        return self.coordinator_data.get("connection_status", "unknown")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "server_url": self.coordinator_data.get(CONF_SERVER_URL),
            "last_response": self.coordinator_data.get("last_response"),
        }


class SolarAcceleratorLastSentSensor(SolarAcceleratorSensorBase):
    """Sensor for last data sent timestamp."""

    _attr_icon = "mdi:clock-outline"
    _attr_translation_key = "last_sent"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Initialize."""
        super().__init__(hass, entry, coordinator_data, "last_sent")
        self._attr_name = "Ostatnie wysłanie"

    @property
    def native_value(self) -> str | None:
        """Return the state."""
        return self.coordinator_data.get("last_sent")


class SolarAcceleratorNextScheduledSensor(SolarAcceleratorSensorBase):
    """Sensor for next scheduled send time."""

    _attr_icon = "mdi:clock-fast"
    _attr_translation_key = "next_scheduled"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Initialize."""
        super().__init__(hass, entry, coordinator_data, "next_scheduled")
        self._attr_name = "Następne wysłanie"

    @property
    def native_value(self) -> str | None:
        """Return the state."""
        return self.coordinator_data.get("next_scheduled")


class SolarAcceleratorEntitiesCountSensor(SolarAcceleratorSensorBase):
    """Sensor for entities count."""

    _attr_icon = "mdi:counter"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "entities_sent"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Initialize."""
        super().__init__(hass, entry, coordinator_data, "entities_sent")
        self._attr_name = "Wysłane encje"

    @property
    def native_value(self) -> int:
        """Return the state."""
        return self.coordinator_data.get("entities_sent", 0)


# Price sensors

class SolarAcceleratorCurrentBuyPriceSensor(SolarAcceleratorSensorBase):
    """Sensor for current buy energy price."""

    _attr_icon = "mdi:cash-minus"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "zł/kWh"
    _attr_translation_key = "current_buy_price"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Initialize."""
        super().__init__(hass, entry, coordinator_data, "current_buy_price")
        self._attr_name = "Cena zakupu energii"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        prices = self.coordinator_data.get("prices", {})
        return prices.get("current_buy_price")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        prices = self.coordinator_data.get("prices", {})
        return {
            "is_cheap": prices.get("is_cheap"),
            "is_expensive": prices.get("is_expensive"),
            "current_hour": prices.get("current_hour"),
            "currency": prices.get("currency"),
            "updated_at": prices.get("updated_at"),
        }


class SolarAcceleratorMinBuyPriceSensor(SolarAcceleratorSensorBase):
    """Sensor for minimum buy price today."""

    _attr_icon = "mdi:arrow-down-bold"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "zł/kWh"
    _attr_translation_key = "min_buy_price"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Initialize."""
        super().__init__(hass, entry, coordinator_data, "min_buy_price")
        self._attr_name = "Min cena zakupu dziś"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        prices = self.coordinator_data.get("prices", {})
        return prices.get("min_buy_price")


class SolarAcceleratorMaxBuyPriceSensor(SolarAcceleratorSensorBase):
    """Sensor for maximum buy price today."""

    _attr_icon = "mdi:arrow-up-bold"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "zł/kWh"
    _attr_translation_key = "max_buy_price"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Initialize."""
        super().__init__(hass, entry, coordinator_data, "max_buy_price")
        self._attr_name = "Max cena zakupu dziś"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        prices = self.coordinator_data.get("prices", {})
        return prices.get("max_buy_price")


class SolarAcceleratorAverageBuyPriceSensor(SolarAcceleratorSensorBase):
    """Sensor for average buy price today."""

    _attr_icon = "mdi:chart-line"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "zł/kWh"
    _attr_translation_key = "average_buy_price"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Initialize."""
        super().__init__(hass, entry, coordinator_data, "average_buy_price")
        self._attr_name = "Średnia cena zakupu dziś"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        prices = self.coordinator_data.get("prices", {})
        return prices.get("average_buy_price")


class SolarAcceleratorIsCheapSensor(SolarAcceleratorSensorBase):
    """Sensor for cheap energy indicator."""

    _attr_icon = "mdi:cash-check"
    _attr_translation_key = "is_cheap"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Initialize."""
        super().__init__(hass, entry, coordinator_data, "is_cheap")
        self._attr_name = "Tania energia"

    @property
    def native_value(self) -> bool | None:
        """Return the state."""
        prices = self.coordinator_data.get("prices", {})
        return prices.get("is_cheap")


class SolarAcceleratorIsExpensiveSensor(SolarAcceleratorSensorBase):
    """Sensor for expensive energy indicator."""

    _attr_icon = "mdi:cash-remove"
    _attr_translation_key = "is_expensive"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Initialize."""
        super().__init__(hass, entry, coordinator_data, "is_expensive")
        self._attr_name = "Droga energia"

    @property
    def native_value(self) -> bool | None:
        """Return the state."""
        prices = self.coordinator_data.get("prices", {})
        return prices.get("is_expensive")


class SolarAcceleratorPriceProviderSensor(SolarAcceleratorSensorBase):
    """Sensor for price provider."""

    _attr_icon = "mdi:domain"
    _attr_translation_key = "price_provider"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Initialize."""
        super().__init__(hass, entry, coordinator_data, "price_provider")
        self._attr_name = "Dostawca cen"

    @property
    def native_value(self) -> str | None:
        """Return the state."""
        prices = self.coordinator_data.get("prices", {})
        return prices.get("provider")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "prices_last_update": self.coordinator_data.get("prices_last_update"),
        }


# Sell price sensors

class SolarAcceleratorCurrentSellPriceSensor(SolarAcceleratorSensorBase):
    """Sensor for current sell energy price."""

    _attr_icon = "mdi:cash-plus"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "zł/kWh"
    _attr_translation_key = "current_sell_price"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Initialize."""
        super().__init__(hass, entry, coordinator_data, "current_sell_price")
        self._attr_name = "Cena sprzedaży energii"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        prices = self.coordinator_data.get("prices", {})
        return prices.get("current_sell_price")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        prices = self.coordinator_data.get("prices", {})
        return {
            "current_hour": prices.get("current_hour"),
            "currency": prices.get("currency"),
            "updated_at": prices.get("updated_at"),
        }


class SolarAcceleratorMinSellPriceSensor(SolarAcceleratorSensorBase):
    """Sensor for minimum sell price today."""

    _attr_icon = "mdi:arrow-down-bold"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "zł/kWh"
    _attr_translation_key = "min_sell_price"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Initialize."""
        super().__init__(hass, entry, coordinator_data, "min_sell_price")
        self._attr_name = "Min cena sprzedaży dziś"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        prices = self.coordinator_data.get("prices", {})
        return prices.get("min_sell_price")


class SolarAcceleratorMaxSellPriceSensor(SolarAcceleratorSensorBase):
    """Sensor for maximum sell price today."""

    _attr_icon = "mdi:arrow-up-bold"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "zł/kWh"
    _attr_translation_key = "max_sell_price"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Initialize."""
        super().__init__(hass, entry, coordinator_data, "max_sell_price")
        self._attr_name = "Max cena sprzedaży dziś"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        prices = self.coordinator_data.get("prices", {})
        return prices.get("max_sell_price")


class SolarAcceleratorAverageSellPriceSensor(SolarAcceleratorSensorBase):
    """Sensor for average sell price today."""

    _attr_icon = "mdi:chart-line"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "zł/kWh"
    _attr_translation_key = "average_sell_price"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Initialize."""
        super().__init__(hass, entry, coordinator_data, "average_sell_price")
        self._attr_name = "Średnia cena sprzedaży dziś"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        prices = self.coordinator_data.get("prices", {})
        return prices.get("average_sell_price")


# Profit sensors

class SolarAcceleratorDailyProfitSensor(SolarAcceleratorSensorBase):
    """Sensor for daily profit from PV installation."""

    _attr_icon = "mdi:cash-multiple"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "PLN"
    _attr_translation_key = "daily_profit"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Initialize."""
        super().__init__(hass, entry, coordinator_data, "daily_profit")
        self._attr_name = "Dzienny zysk"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        profit = self.coordinator_data.get("profit", {})
        return profit.get("daily_profit_pln")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        profit = self.coordinator_data.get("profit", {})
        return {
            "date": profit.get("date"),
            "battery_value_pln": profit.get("battery_value_pln"),
            "battery_avg_price_pln": profit.get("battery_avg_price_pln"),
            "currency": profit.get("currency"),
        }


class SolarAcceleratorBatteryValueSensor(SolarAcceleratorSensorBase):
    """Sensor for current battery energy value."""

    _attr_icon = "mdi:battery-charging"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "PLN"
    _attr_translation_key = "battery_value"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Initialize."""
        super().__init__(hass, entry, coordinator_data, "battery_value")
        self._attr_name = "Wartość baterii"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        profit = self.coordinator_data.get("profit", {})
        return profit.get("battery_value_pln")


class SolarAcceleratorBatteryAvgPriceSensor(SolarAcceleratorSensorBase):
    """Sensor for average price of energy stored in battery."""

    _attr_icon = "mdi:battery-clock"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "PLN/kWh"
    _attr_translation_key = "battery_avg_price"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Initialize."""
        super().__init__(hass, entry, coordinator_data, "battery_avg_price")
        self._attr_name = "Średnia cena baterii"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        profit = self.coordinator_data.get("profit", {})
        return profit.get("battery_avg_price_pln")


def convert_value(value: str | None, entity_key: str) -> float | int | bool | str | None:
    """Convert entity value to appropriate type for API."""
    if value is None or value in ("unknown", "unavailable", ""):
        return 0

    if entity_key == "grid_connected_status":
        return value.lower() in ("on", "true", "1", "connected")

    if entity_key == "inverter_status":
        return value

    try:
        float_val = float(value)
        if float_val.is_integer():
            return int(float_val)
        return float_val
    except (ValueError, TypeError):
        return 0


def get_next_full_hour() -> datetime:
    """Get the next full hour timestamp."""
    now = dt_util.now()
    next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return next_hour


def get_seconds_until_next_hour() -> float:
    """Get seconds until the next full hour."""
    now = dt_util.now()
    next_hour = get_next_full_hour()
    return (next_hour - now).total_seconds()


async def async_send_data(
    hass: HomeAssistant,
    coordinator_data: dict[str, Any],
) -> bool:
    """Send data to server. Returns True on success."""
    api_key = coordinator_data.get(CONF_API_KEY)
    server_url = coordinator_data.get(CONF_SERVER_URL)
    entity_mapping = coordinator_data.get(CONF_ENTITY_MAPPING, {})

    session = async_get_clientsession(hass)
    endpoint = f"{server_url}{API_SEND_DATA_ENDPOINT}"

    try:
        entities_data = {}
        entities_count = 0

        for entity_key in ENTITY_KEYS:
            ha_entity_id = entity_mapping.get(entity_key)
            if ha_entity_id:
                state = hass.states.get(ha_entity_id)
                if state:
                    value = convert_value(state.state, entity_key)
                    entities_data[entity_key] = value
                    entities_count += 1
                else:
                    entities_data[entity_key] = 0
            else:
                entities_data[entity_key] = 0

        payload = {
            "timestamp": dt_util.utcnow().isoformat(),
            "entityPrefix": coordinator_data.get(CONF_SOLARMAN_PREFIX, ""),
            "entities": entities_data,
        }

        async with session.post(
            endpoint,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            response_text = await resp.text()

            if resp.status == 200:
                coordinator_data["last_sent"] = dt_util.now().strftime("%Y-%m-%d %H:%M:%S")
                coordinator_data["connection_status"] = "connected"
                coordinator_data["entities_sent"] = entities_count
                coordinator_data["last_response"] = "OK"
                _LOGGER.info(
                    "Data sent successfully to %s: %d entities",
                    endpoint,
                    entities_count,
                )
                return True
            elif resp.status == 401:
                coordinator_data["connection_status"] = "auth_error"
                coordinator_data["last_response"] = "Nieprawidłowy klucz API"
                _LOGGER.error("Authentication failed: invalid API key")
            else:
                coordinator_data["connection_status"] = "error"
                coordinator_data["last_response"] = f"HTTP {resp.status}: {response_text[:100]}"
                _LOGGER.error(
                    "Failed to send data: %s - %s",
                    resp.status,
                    response_text,
                )

    except aiohttp.ClientError as e:
        coordinator_data["connection_status"] = "disconnected"
        coordinator_data["last_response"] = f"Connection error: {str(e)[:50]}"
        _LOGGER.error("Connection error: %s", e)
    except Exception as e:
        coordinator_data["connection_status"] = "error"
        coordinator_data["last_response"] = f"Error: {str(e)[:50]}"
        _LOGGER.exception("Error sending data: %s", e)

    return False


async def async_fetch_prices(
    hass: HomeAssistant,
    coordinator_data: dict[str, Any],
) -> bool:
    """Fetch prices from server. Returns True on success."""
    api_key = coordinator_data.get(CONF_API_KEY)
    server_url = coordinator_data.get(CONF_SERVER_URL)

    session = async_get_clientsession(hass)
    endpoint = f"{server_url}{API_PRICES_ENDPOINT}"

    try:
        async with session.get(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
            },
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                coordinator_data["prices"] = {
                    # Ceny zakupu
                    "current_buy_price": data.get("current_buy_price"),
                    "min_buy_price": data.get("min_buy_price"),
                    "max_buy_price": data.get("max_buy_price"),
                    "average_buy_price": data.get("average_buy_price"),
                    # Ceny sprzedaży
                    "current_sell_price": data.get("current_sell_price"),
                    "min_sell_price": data.get("min_sell_price"),
                    "max_sell_price": data.get("max_sell_price"),
                    "average_sell_price": data.get("average_sell_price"),
                    # Metadane
                    "currency": data.get("currency"),
                    "unit": data.get("unit"),
                    "current_hour": data.get("current_hour"),
                    "is_cheap": data.get("is_cheap"),
                    "is_expensive": data.get("is_expensive"),
                    "provider": data.get("provider"),
                    "updated_at": data.get("updated_at"),
                }
                coordinator_data["prices_last_update"] = dt_util.now().strftime("%Y-%m-%d %H:%M:%S")
                _LOGGER.info("Prices fetched successfully from %s", endpoint)
                return True
            elif resp.status == 404:
                _LOGGER.warning("No price data available: %s", await resp.text())
            else:
                _LOGGER.error("Failed to fetch prices: %s", resp.status)

    except aiohttp.ClientError as e:
        _LOGGER.error("Connection error fetching prices: %s", e)
    except Exception as e:
        _LOGGER.exception("Error fetching prices: %s", e)

    return False


async def async_fetch_profit(
    hass: HomeAssistant,
    coordinator_data: dict[str, Any],
) -> bool:
    """Fetch daily profit from server. Returns True on success."""
    api_key = coordinator_data.get(CONF_API_KEY)
    server_url = coordinator_data.get(CONF_SERVER_URL)

    session = async_get_clientsession(hass)
    endpoint = f"{server_url}{API_PROFIT_ENDPOINT}"

    try:
        async with session.get(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
            },
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                coordinator_data["profit"] = {
                    "date": data.get("date"),
                    "daily_profit_pln": data.get("daily_profit_pln"),
                    "battery_value_pln": data.get("battery_value_pln"),
                    "battery_avg_price_pln": data.get("battery_avg_price_pln"),
                    "currency": data.get("currency"),
                }
                coordinator_data["profit_last_update"] = dt_util.now().strftime("%Y-%m-%d %H:%M:%S")
                _LOGGER.info("Profit data fetched successfully from %s", endpoint)
                return True
            elif resp.status == 404:
                _LOGGER.warning("No profit data available: %s", await resp.text())
            else:
                _LOGGER.error("Failed to fetch profit: %s", resp.status)

    except aiohttp.ClientError as e:
        _LOGGER.error("Connection error fetching profit: %s", e)
    except Exception as e:
        _LOGGER.exception("Error fetching profit: %s", e)

    return False


async def async_send_data_hourly(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator_data: dict[str, Any],
) -> None:
    """Send data to server at every full hour."""

    while True:
        try:
            # Calculate time until next full hour
            seconds_to_wait = get_seconds_until_next_hour()
            next_scheduled = get_next_full_hour()
            coordinator_data["next_scheduled"] = next_scheduled.strftime("%Y-%m-%d %H:%M:%S")

            _LOGGER.debug(
                "Next data send scheduled for %s (in %.0f seconds)",
                next_scheduled,
                seconds_to_wait,
            )

            # Wait until next full hour
            await asyncio.sleep(seconds_to_wait)

            # Send data and fetch prices and profit
            await async_send_data(hass, coordinator_data)
            await async_fetch_prices(hass, coordinator_data)
            await async_fetch_profit(hass, coordinator_data)

        except asyncio.CancelledError:
            _LOGGER.debug("Hourly data sending task cancelled")
            break
        except Exception as e:
            _LOGGER.exception("Error in hourly send task: %s", e)
            # Wait a minute before retrying
            await asyncio.sleep(60)
