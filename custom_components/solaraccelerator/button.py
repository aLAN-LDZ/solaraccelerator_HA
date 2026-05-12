"""Platforma button — przycisk manualnej synchronizacji z backendem.

Daje użytkownikowi możliwość wymuszenia wysyłki danych poza harmonogramem godzinowym.
Przydatne do debugowania (np. po zmianie mapowania encji) albo gdy ktoś chce
sprawdzić działanie integracji bez czekania na pełną godzinę.

Przycisk wykonuje to samo co krok 1 i 2 pętli godzinowej:
``async_send_data`` + ``async_fetch_prices``. NIE wykonuje pollingu data-ready
ani fetcha profitu — to zostawiamy zaplanowanej pętli.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import async_fetch_prices, async_send_data
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Zarejestruj przycisk synchronizacji."""

    coordinator_data = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([
        SolarAcceleratorSyncButton(hass, entry, coordinator_data),
    ])


class SolarAcceleratorSyncButton(ButtonEntity):
    """Przycisk do ręcznej synchronizacji danych z backendem Solar Accelerator."""

    _attr_icon = "mdi:sync"
    _attr_translation_key = "sync"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator_data: dict[str, Any],
    ) -> None:
        """Zainicjalizuj przycisk synchronizacji."""
        self.hass = hass
        self.entry = entry
        self.coordinator_data = coordinator_data
        self._attr_unique_id = f"{entry.entry_id}_sync"
        self._attr_name = "Synchronizuj"

    @property
    def device_info(self) -> DeviceInfo:
        """Zwróć informacje o urządzeniu — wspólne z sensorami pod jednym wpisem."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name="Solar Accelerator",
            manufacturer="Solar Accelerator",
            model="Home Assistant Integration",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_press(self) -> None:
        """Obsługa naciśnięcia: wyślij paczkę i pobierz ceny od razu."""
        _LOGGER.info("Ręczna synchronizacja z Solar Accelerator")
        await async_send_data(self.hass, self.coordinator_data)
        await async_fetch_prices(self.hass, self.coordinator_data)
