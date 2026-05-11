"""Sensory cen energii — zakup, sprzedaż i flagi tania/droga energia.

Dane pochodzą z ``coordinator_data["prices"]``, którą uzupełnia ``async_fetch_prices``
co godzinę oraz na starcie integracji. Sensory tylko czytają z tego słownika —
nie robią własnych zapytań HTTP.

Konwencja: cena ``current_buy_price`` to cena KUPNA energii z sieci (koszt importu),
``current_sell_price`` to cena SPRZEDAŻY (przychód z eksportu).
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ._base import SolarAcceleratorSensorBase


# === Ceny zakupu energii (kupno z sieci) ===


class SolarAcceleratorCurrentBuyPriceSensor(SolarAcceleratorSensorBase):
    """Aktualna cena zakupu energii (zł/kWh) z atrybutami: is_cheap/is_expensive."""

    _attr_icon = "mdi:cash-minus"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "zł/kWh"
    _attr_translation_key = "current_buy_price"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj sensor aktualnej ceny zakupu."""
        super().__init__(hass, entry, coordinator_data, "current_buy_price")
        self._attr_name = "Cena zakupu energii"

    @property
    def native_value(self) -> float | None:
        """Zwróć aktualną cenę zakupu z ostatnio pobranych danych."""
        prices = self.coordinator_data.get("prices", {})
        return prices.get("current_buy_price")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Dodatkowe pola pomocne w automatyzacjach (flagi, godzina, waluta)."""
        prices = self.coordinator_data.get("prices", {})
        return {
            "is_cheap": prices.get("is_cheap"),
            "is_expensive": prices.get("is_expensive"),
            "current_hour": prices.get("current_hour"),
            "currency": prices.get("currency"),
            "updated_at": prices.get("updated_at"),
        }


class SolarAcceleratorMinBuyPriceSensor(SolarAcceleratorSensorBase):
    """Minimalna cena zakupu w bieżącej dobie."""

    _attr_icon = "mdi:arrow-down-bold"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "zł/kWh"
    _attr_translation_key = "min_buy_price"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj sensor minimalnej ceny zakupu."""
        super().__init__(hass, entry, coordinator_data, "min_buy_price")
        self._attr_name = "Min cena zakupu dziś"

    @property
    def native_value(self) -> float | None:
        """Zwróć minimum z dzisiejszych cen zakupu."""
        prices = self.coordinator_data.get("prices", {})
        return prices.get("min_buy_price")


class SolarAcceleratorMaxBuyPriceSensor(SolarAcceleratorSensorBase):
    """Maksymalna cena zakupu w bieżącej dobie."""

    _attr_icon = "mdi:arrow-up-bold"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "zł/kWh"
    _attr_translation_key = "max_buy_price"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj sensor maksymalnej ceny zakupu."""
        super().__init__(hass, entry, coordinator_data, "max_buy_price")
        self._attr_name = "Max cena zakupu dziś"

    @property
    def native_value(self) -> float | None:
        """Zwróć maksimum z dzisiejszych cen zakupu."""
        prices = self.coordinator_data.get("prices", {})
        return prices.get("max_buy_price")


class SolarAcceleratorAverageBuyPriceSensor(SolarAcceleratorSensorBase):
    """Średnia cena zakupu z całej doby."""

    _attr_icon = "mdi:chart-line"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "zł/kWh"
    _attr_translation_key = "average_buy_price"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj sensor średniej ceny zakupu."""
        super().__init__(hass, entry, coordinator_data, "average_buy_price")
        self._attr_name = "Średnia cena zakupu dziś"

    @property
    def native_value(self) -> float | None:
        """Zwróć średnią z dzisiejszych cen zakupu."""
        prices = self.coordinator_data.get("prices", {})
        return prices.get("average_buy_price")


# === Ceny sprzedaży energii (oddawanie do sieci) ===


class SolarAcceleratorCurrentSellPriceSensor(SolarAcceleratorSensorBase):
    """Aktualna cena sprzedaży energii (zł/kWh)."""

    _attr_icon = "mdi:cash-plus"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "zł/kWh"
    _attr_translation_key = "current_sell_price"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj sensor aktualnej ceny sprzedaży."""
        super().__init__(hass, entry, coordinator_data, "current_sell_price")
        self._attr_name = "Cena sprzedaży energii"

    @property
    def native_value(self) -> float | None:
        """Zwróć aktualną cenę sprzedaży."""
        prices = self.coordinator_data.get("prices", {})
        return prices.get("current_sell_price")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Dodatkowe pola: bieżąca godzina, waluta, czas aktualizacji."""
        prices = self.coordinator_data.get("prices", {})
        return {
            "current_hour": prices.get("current_hour"),
            "currency": prices.get("currency"),
            "updated_at": prices.get("updated_at"),
        }


class SolarAcceleratorMinSellPriceSensor(SolarAcceleratorSensorBase):
    """Minimalna cena sprzedaży w bieżącej dobie."""

    _attr_icon = "mdi:arrow-down-bold"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "zł/kWh"
    _attr_translation_key = "min_sell_price"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj sensor minimalnej ceny sprzedaży."""
        super().__init__(hass, entry, coordinator_data, "min_sell_price")
        self._attr_name = "Min cena sprzedaży dziś"

    @property
    def native_value(self) -> float | None:
        """Zwróć minimum z dzisiejszych cen sprzedaży."""
        prices = self.coordinator_data.get("prices", {})
        return prices.get("min_sell_price")


class SolarAcceleratorMaxSellPriceSensor(SolarAcceleratorSensorBase):
    """Maksymalna cena sprzedaży w bieżącej dobie."""

    _attr_icon = "mdi:arrow-up-bold"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "zł/kWh"
    _attr_translation_key = "max_sell_price"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj sensor maksymalnej ceny sprzedaży."""
        super().__init__(hass, entry, coordinator_data, "max_sell_price")
        self._attr_name = "Max cena sprzedaży dziś"

    @property
    def native_value(self) -> float | None:
        """Zwróć maksimum z dzisiejszych cen sprzedaży."""
        prices = self.coordinator_data.get("prices", {})
        return prices.get("max_sell_price")


class SolarAcceleratorAverageSellPriceSensor(SolarAcceleratorSensorBase):
    """Średnia cena sprzedaży z całej doby."""

    _attr_icon = "mdi:chart-line"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "zł/kWh"
    _attr_translation_key = "average_sell_price"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj sensor średniej ceny sprzedaży."""
        super().__init__(hass, entry, coordinator_data, "average_sell_price")
        self._attr_name = "Średnia cena sprzedaży dziś"

    @property
    def native_value(self) -> float | None:
        """Zwróć średnią z dzisiejszych cen sprzedaży."""
        prices = self.coordinator_data.get("prices", {})
        return prices.get("average_sell_price")


# === Flagi i metadane cen ===


class SolarAcceleratorIsCheapSensor(SolarAcceleratorSensorBase):
    """Flaga: czy bieżąca godzina jest oznaczona jako "tania" (do automatyzacji)."""

    _attr_icon = "mdi:cash-check"
    _attr_translation_key = "is_cheap"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj sensor flagi taniej energii."""
        super().__init__(hass, entry, coordinator_data, "is_cheap")
        self._attr_name = "Tania energia"

    @property
    def native_value(self) -> bool | None:
        """Zwróć flagę taniej energii ustaloną przez backend."""
        prices = self.coordinator_data.get("prices", {})
        return prices.get("is_cheap")


class SolarAcceleratorIsExpensiveSensor(SolarAcceleratorSensorBase):
    """Flaga: czy bieżąca godzina jest oznaczona jako "droga"."""

    _attr_icon = "mdi:cash-remove"
    _attr_translation_key = "is_expensive"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj sensor flagi drogiej energii."""
        super().__init__(hass, entry, coordinator_data, "is_expensive")
        self._attr_name = "Droga energia"

    @property
    def native_value(self) -> bool | None:
        """Zwróć flagę drogiej energii."""
        prices = self.coordinator_data.get("prices", {})
        return prices.get("is_expensive")


class SolarAcceleratorPriceProviderSensor(SolarAcceleratorSensorBase):
    """Nazwa dostawcy cen z którego pochodzą wartości (np. TGE, Tauron)."""

    _attr_icon = "mdi:domain"
    _attr_translation_key = "price_provider"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj sensor dostawcy cen."""
        super().__init__(hass, entry, coordinator_data, "price_provider")
        self._attr_name = "Dostawca cen"

    @property
    def native_value(self) -> str | None:
        """Zwróć nazwę dostawcy cen energii."""
        prices = self.coordinator_data.get("prices", {})
        return prices.get("provider")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Dodatkowe pole: kiedy ostatnio pobraliśmy ceny z backendu."""
        return {
            "prices_last_update": self.coordinator_data.get("prices_last_update"),
        }
