"""Platforma binary_sensor — stany dwustanowe integracji.

Aktualnie jeden sensor:

- **Komunikacja z falownikiem** (device_class ``connectivity``) — pokazuje status
  łącza falownik ↔ Home Assistant wykrywany na podstawie "parametrów życiowych"
  (napięcia + częstotliwość). ``on`` = połączony, ``off`` = utracona komunikacja.
  Logika i debounce żyją w ``health.py``; ten sensor tylko prezentuje wynik
  z ``coordinator_data["inverter_online"]`` i odświeża się natychmiast przy zmianie
  (callback ``inverter_health_notify``).
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Zarejestruj sensory dwustanowe integracji."""
    coordinator_data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SolarAcceleratorInverterCommsSensor(hass, entry, coordinator_data)])


class SolarAcceleratorInverterCommsSensor(BinarySensorEntity):
    """Status komunikacji falownik ↔ Home Assistant."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "inverter_comms"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj sensor — czyta status z coordinator_data."""
        self.hass = hass
        self.entry = entry
        self.coordinator_data = coordinator_data
        self._attr_unique_id = f"{entry.entry_id}_inverter_comms"
        self._attr_name = "Komunikacja z falownikiem"

    @property
    def device_info(self) -> DeviceInfo:
        """Wspólne urządzenie z resztą encji integracji."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name="Solar Accelerator",
            manufacturer="Solar Accelerator",
            model="Home Assistant Integration",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def is_on(self) -> bool:
        """``True`` = falownik połączony (connectivity: on = connected)."""
        return bool(self.coordinator_data.get("inverter_online", True))

    async def async_added_to_hass(self) -> None:
        """Podłącz callback natychmiastowego odświeżania przy zmianie statusu."""
        await super().async_added_to_hass()
        self.coordinator_data["inverter_health_notify"] = self._handle_health_change

    async def async_will_remove_from_hass(self) -> None:
        """Odepnij callback przy usuwaniu encji."""
        if self.coordinator_data.get("inverter_health_notify") is self._handle_health_change:
            self.coordinator_data["inverter_health_notify"] = None
        await super().async_will_remove_from_hass()

    @callback
    def _handle_health_change(self) -> None:
        """Wywoływane przez health.update_inverter_health przy przełączeniu statusu."""
        self.async_write_ha_state()
