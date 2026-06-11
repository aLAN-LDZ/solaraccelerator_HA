"""Platforma switch — przełączniki sterujące zachowaniem integracji.

Aktualnie jeden przełącznik:

- **Pilnuj ustawień** — gdy ON, integracja po każdej komendzie z backendu zapamiętuje
  docelowy stan sterowanych encji i pilnuje go przez całą godzinę. Jeśli falownik
  sam wróci do wcześniejszej wartości (znany problem Deye/Solarman po Modbusie —
  rejestr potrafi zresetować się po kilku–kilkunastu minutach), guard natychmiast
  wysyła komendę przywracającą wartość z planu. Bez tego plan optymalizatora bywa
  niezrealizowany mimo że komenda raz się wykonała.

Encja używa ``RestoreEntity`` (stan przeżywa restart HA) i ``EntityCategory.CONFIG``
(grupowana z encjami konfiguracyjnymi, nie z głównymi sensorami). Domyślnie ON.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DATA_GUARD_ENABLED, DEFAULT_GUARD_ENABLED, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Zarejestruj przełączniki integracji."""
    coordinator_data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SolarAcceleratorGuardSwitch(hass, entry, coordinator_data)])


class SolarAcceleratorGuardSwitch(SwitchEntity, RestoreEntity):
    """Przełącznik "Pilnuj ustawień" — włącza/wyłącza przywracanie wartości z planu."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:shield-sync"
    _attr_translation_key = "guard_enabled"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj encję — wartość początkowa z coordinator_data (lub default)."""
        self.hass = hass
        self.entry = entry
        self.coordinator_data = coordinator_data
        self._attr_unique_id = f"{entry.entry_id}_guard_enabled"
        self._attr_name = "Pilnuj ustawień"
        coordinator_data.setdefault(DATA_GUARD_ENABLED, DEFAULT_GUARD_ENABLED)
        self._attr_is_on = bool(coordinator_data[DATA_GUARD_ENABLED])

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

    async def async_added_to_hass(self) -> None:
        """Po dodaniu do HA odtwórz ostatni stan (przeżywa restart)."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in ("on", "off"):
            is_on = last.state == "on"
            self._attr_is_on = is_on
            self.coordinator_data[DATA_GUARD_ENABLED] = is_on
            _LOGGER.debug("Odtworzono Pilnuj ustawień = %s", is_on)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Włącz pilnowanie ustawień."""
        self._apply(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Wyłącz pilnowanie ustawień."""
        self._apply(False)

    def _apply(self, value: bool) -> None:
        """Zapisz nowy stan w encji i coordinator_data; przy OFF wyczyść korekty w locie."""
        self._attr_is_on = value
        self.coordinator_data[DATA_GUARD_ENABLED] = value
        if not value and (guard := self.coordinator_data.get("settings_guard")):
            guard.clear_pending()
        self.async_write_ha_state()
        _LOGGER.info("Pilnuj ustawień: %s", "włączone" if value else "wyłączone")
