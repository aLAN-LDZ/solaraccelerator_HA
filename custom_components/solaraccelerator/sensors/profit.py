"""Sensory zysku dziennego i wyceny energii w baterii.

Wartości wyliczane są po stronie serwera na podstawie danych godzinowych — klient
ich nie liczy. Dane pochodzą z ``coordinator_data["profit"]`` uzupełnianego przez
``async_fetch_profit`` po potwierdzeniu data-ready w pętli godzinowej.

Konwencja:
- ``daily_profit_pln``      — sumaryczny dzienny bilans (eksport - import + zmiana wartości baterii),
- ``battery_value_pln``     — bieżąca wartość energii w baterii (ile kosztowała),
- ``battery_avg_price_pln`` — średnia cena za którą energia w baterii została kupiona/wytworzona.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ._base import SolarAcceleratorSensorBase


class SolarAcceleratorDailyProfitSensor(SolarAcceleratorSensorBase):
    """Bilans finansowy dnia (eksport - import + zmiana wartości baterii) w PLN."""

    _attr_icon = "mdi:cash-multiple"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "PLN"
    _attr_translation_key = "daily_profit"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj sensor dziennego zysku."""
        super().__init__(hass, entry, coordinator_data, "daily_profit")
        self._attr_name = "Dzienny zysk"

    @property
    def native_value(self) -> float | None:
        """Zwróć dzienny zysk wyliczony przez backend."""
        profit = self.coordinator_data.get("profit", {})
        return profit.get("daily_profit_pln")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Dodatkowe pola: data, wartość baterii i waluta — pełen kontekst w jednym miejscu."""
        profit = self.coordinator_data.get("profit", {})
        return {
            "date": profit.get("date"),
            "battery_value_pln": profit.get("battery_value_pln"),
            "battery_avg_price_pln": profit.get("battery_avg_price_pln"),
            "currency": profit.get("currency"),
        }


class SolarAcceleratorBatteryValueSensor(SolarAcceleratorSensorBase):
    """Wartość energii zgromadzonej w baterii (PLN) — ile kosztowało jej naładowanie."""

    _attr_icon = "mdi:battery-charging"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "PLN"
    _attr_translation_key = "battery_value"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj sensor wartości baterii."""
        super().__init__(hass, entry, coordinator_data, "battery_value")
        self._attr_name = "Wartość baterii"

    @property
    def native_value(self) -> float | None:
        """Zwróć wartość energii w baterii w PLN."""
        profit = self.coordinator_data.get("profit", {})
        return profit.get("battery_value_pln")


class SolarAcceleratorBatteryAvgPriceSensor(SolarAcceleratorSensorBase):
    """Średnia cena energii zgromadzonej w baterii (PLN/kWh).

    Użyteczne do decyzji o rozładowaniu: jeśli aktualna cena rynkowa jest wyższa
    od średniej z baterii, opłaca się sprzedawać/zużywać. Liczone po stronie backendu
    na podstawie cykli ładowania.
    """

    _attr_icon = "mdi:battery-clock"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "PLN/kWh"
    _attr_translation_key = "battery_avg_price"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj sensor średniej ceny baterii."""
        super().__init__(hass, entry, coordinator_data, "battery_avg_price")
        self._attr_name = "Średnia cena baterii"

    @property
    def native_value(self) -> float | None:
        """Zwróć średnią cenę energii w baterii."""
        profit = self.coordinator_data.get("profit", {})
        return profit.get("battery_avg_price_pln")
