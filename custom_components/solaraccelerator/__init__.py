"""The Solar Accelerator integration."""
from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_SERVER_URL,
    CONF_ENTITY_MAPPING,
)

LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "button"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Solar Accelerator from a config entry."""

    hass.data.setdefault(DOMAIN, {})

    hass.data[DOMAIN][entry.entry_id] = {
        CONF_API_KEY: entry.data.get(CONF_API_KEY),
        CONF_SERVER_URL: entry.data.get(CONF_SERVER_URL),
        CONF_ENTITY_MAPPING: entry.data.get(CONF_ENTITY_MAPPING, {}),
        "last_sent": None,
        "next_scheduled": None,
        "last_response": None,
        "connection_status": "unknown",
        "entities_sent": 0,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Cancel the hourly task if running
    coordinator_data = hass.data[DOMAIN].get(entry.entry_id, {})
    if task := coordinator_data.get("_task"):
        task.cancel()

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
