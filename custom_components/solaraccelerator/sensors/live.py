"""Sensory diagnostyczne kanału live (szybki push + odbiór komend).

Wszystkie trzy mają kategorię ``DIAGNOSTIC`` — w UI pojawiają się w sekcji
"Diagnostyka". Czytają stan z ``coordinator_data``, który aktualizuje pętla
``async_send_live_data_loop`` po każdym pushu.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant

from ..const import DEFAULT_LIVE_INTERVAL
from ._base import SolarAcceleratorSensorBase


class SolarAcceleratorLiveStatusSensor(SolarAcceleratorSensorBase):
    """Status kanału live: ``live``/``disabled``/``rate_limited``/``auth_error``/``error``.

    Pokazuje co dzieje się z szybkim kanałem komunikacji. ``inactive`` na starcie
    przed pierwszym pushem.
    """

    _attr_icon = "mdi:broadcast"
    _attr_translation_key = "live_status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj sensor statusu kanału live."""
        super().__init__(hass, entry, coordinator_data, "live_status")
        self._attr_name = "Status LIVE"

    @property
    def native_value(self) -> str:
        """Zwróć aktualny status kanału live."""
        return self.coordinator_data.get("live_status", "inactive")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Dodatkowe pola: ustawiony interwał i czas ostatniego pushu."""
        return {
            "live_interval_seconds": self.coordinator_data.get("live_interval_seconds"),
            "live_last_push": self.coordinator_data.get("live_last_push"),
        }


class SolarAcceleratorLiveLastPushSensor(SolarAcceleratorSensorBase):
    """Znacznik czasu ostatniego udanego pushu na endpoint /live."""

    _attr_icon = "mdi:clock-fast"
    _attr_translation_key = "live_last_push"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj sensor ostatniego live pushu."""
        super().__init__(hass, entry, coordinator_data, "live_last_push")
        self._attr_name = "Ostatni push LIVE"

    @property
    def native_value(self) -> str | None:
        """Zwróć czas ostatniego live pushu."""
        return self.coordinator_data.get("live_last_push")


class SolarAcceleratorLiveIntervalSensor(SolarAcceleratorSensorBase):
    """Aktualny interwał między pushami w sekundach — ustawiany przez serwer."""

    _attr_icon = "mdi:timer-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "s"
    _attr_translation_key = "live_interval"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj sensor interwału live."""
        super().__init__(hass, entry, coordinator_data, "live_interval")
        self._attr_name = "Interwał LIVE"

    @property
    def native_value(self) -> int:
        """Zwróć aktualny interwał (domyślny gdy serwer jeszcze nic nie podał)."""
        return self.coordinator_data.get("live_interval_seconds", DEFAULT_LIVE_INTERVAL)
