"""Platforma number — encje konfiguracyjne write_managera.

Dwie encje pozwalające tunować z UI HA opóźnienia w kolejce komend:
- **Command Delay**    — sekund między kolejnymi write w batch'y,
- **Verify Settling**  — sekund od ostatniego write do verify (czas stabilizacji falownika).

Obie encje:
- używają ``RestoreEntity`` — wartości przeżywają restart HA,
- zapisują się w ``coordinator_data`` — write_manager czyta je przy każdej batch'y
  (nie cache'uje, więc zmiany działają natychmiast).

Sensor "developerski" — gdy znajdziemy optymalne wartości, można te encje
ukryć przez ``EntityCategory.CONFIG`` (już ustawione), albo całkiem usunąć
zostawiając wartości jako stałe w kodzie.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DEFAULT_COMMAND_DELAY,
    DEFAULT_VERIFY_RETRIES,
    DEFAULT_VERIFY_SETTLING,
    DOMAIN,
    MAX_COMMAND_DELAY,
    MAX_VERIFY_RETRIES,
    MAX_VERIFY_SETTLING,
    MIN_COMMAND_DELAY,
    MIN_VERIFY_RETRIES,
    MIN_VERIFY_SETTLING,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Zarejestruj encje konfiguracyjne write_managera."""
    coordinator_data = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([
        SolarAcceleratorCommandDelayNumber(hass, entry, coordinator_data),
        SolarAcceleratorVerifySettlingNumber(hass, entry, coordinator_data),
        SolarAcceleratorVerifyRetriesNumber(hass, entry, coordinator_data),
    ])


class _ConfigNumberBase(NumberEntity, RestoreEntity):
    """Wspólna baza dla encji konfiguracyjnych — device_info, persistencja, zapis do coordinator_data."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = "s"

    # Klucz w coordinator_data — nadpisywany w klasie potomnej
    _data_key: str = ""
    # Wartość domyślna gdy nic nie odtworzono i nic nie ma w coordinator_data
    _default_value: float = 0.0

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator_data: dict[str, Any],
        unique_suffix: str,
    ) -> None:
        """Zainicjalizuj wspólne pola encji konfiguracyjnej."""
        self.hass = hass
        self.entry = entry
        self.coordinator_data = coordinator_data
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"
        # Wstępna wartość — write_manager czyta z coordinator_data więc inicjalizujemy od razu
        coordinator_data.setdefault(self._data_key, self._default_value)
        self._attr_native_value = float(coordinator_data[self._data_key])

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
        """Po dodaniu do HA odtwórz ostatnią wartość (przeżywa restart)."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state not in (None, "unknown", "unavailable"):
            try:
                restored = float(last.state)
                self._attr_native_value = restored
                self.coordinator_data[self._data_key] = restored
                _LOGGER.debug(
                    "Odtworzono %s = %s z poprzedniego stanu", self._data_key, restored,
                )
            except (ValueError, TypeError):
                _LOGGER.warning(
                    "Nie udało się sparsować odtworzonej wartości %s: %s",
                    self._data_key, last.state,
                )

    async def async_set_native_value(self, value: float) -> None:
        """Ustaw nową wartość — zapisz w stanie encji i w coordinator_data."""
        self._attr_native_value = value
        self.coordinator_data[self._data_key] = value
        self.async_write_ha_state()
        _LOGGER.info("Zmieniono %s na %s", self._data_key, value)


class SolarAcceleratorCommandDelayNumber(_ConfigNumberBase):
    """Sekund opóźnienia między kolejnymi komendami write w jednej batch'y."""

    _attr_icon = "mdi:timer-sand"
    _attr_translation_key = "command_delay"
    _attr_native_min_value = MIN_COMMAND_DELAY
    _attr_native_max_value = MAX_COMMAND_DELAY
    _attr_native_step = 0.1

    _data_key = "command_delay"
    _default_value = DEFAULT_COMMAND_DELAY

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj encję command_delay."""
        super().__init__(hass, entry, coordinator_data, "command_delay")
        self._attr_name = "Opóźnienie między komendami"


class SolarAcceleratorVerifySettlingNumber(_ConfigNumberBase):
    """Sekund oczekiwania po ostatniej komendzie zanim odczytamy wartości do verify."""

    _attr_icon = "mdi:timer-check"
    _attr_translation_key = "verify_settling"
    _attr_native_min_value = MIN_VERIFY_SETTLING
    _attr_native_max_value = MAX_VERIFY_SETTLING
    _attr_native_step = 0.5

    _data_key = "verify_settling"
    _default_value = DEFAULT_VERIFY_SETTLING

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj encję verify_settling."""
        super().__init__(hass, entry, coordinator_data, "verify_settling")
        self._attr_name = "Opóźnienie przed verify"


class SolarAcceleratorVerifyRetriesNumber(_ConfigNumberBase):
    """Liczba dodatkowych prób execute+verify gdy pierwszy verify się nie powiódł."""

    # Liczba prób — bez jednostki "s"
    _attr_native_unit_of_measurement = None
    _attr_icon = "mdi:reload"
    _attr_translation_key = "verify_retries"
    _attr_native_min_value = MIN_VERIFY_RETRIES
    _attr_native_max_value = MAX_VERIFY_RETRIES
    _attr_native_step = 1

    _data_key = "verify_retries"
    _default_value = DEFAULT_VERIFY_RETRIES

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj encję verify_retries."""
        super().__init__(hass, entry, coordinator_data, "verify_retries")
        self._attr_name = "Liczba prób verify"
