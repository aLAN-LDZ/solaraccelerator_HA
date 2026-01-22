"""Button platform for Solar Accelerator integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import DOMAIN
from .sensor import async_send_data, async_fetch_prices

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button platform."""

    coordinator_data = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([
        SolarAcceleratorSyncButton(hass, entry, coordinator_data),
    ])


class SolarAcceleratorSyncButton(ButtonEntity):
    """Button to synchronize data with SolarAccelerator."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:sync"
    _attr_translation_key = "sync"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator_data: dict[str, Any],
    ) -> None:
        """Initialize the button."""
        self.hass = hass
        self.entry = entry
        self.coordinator_data = coordinator_data
        self._attr_unique_id = f"{entry.entry_id}_sync"
        self._attr_name = "Synchronizuj"

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

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.info("Synchronizing data with SolarAccelerator")
        await async_send_data(self.hass, self.coordinator_data)
        await async_fetch_prices(self.hass, self.coordinator_data)
