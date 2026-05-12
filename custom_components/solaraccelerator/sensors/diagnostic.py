"""Sensory diagnostyczne — stan połączenia z backendem i statystyki wysyłki.

Sensory z tego pliku odpowiadają na pytania typu:
- czy jesteśmy połączeni z serwerem?
- kiedy ostatnio wysłaliśmy paczkę i kiedy będzie kolejna?
- ile encji ma ustawione mapowanie i ile faktycznie ma stan?

Wszystkie mają kategorię ``DIAGNOSTIC`` — w UI HA pojawią się w sekcji
"Diagnostyka" zamiast głównej listy encji.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant

from ..const import (
    CONF_ENTITY_MAPPING,
    CONF_EV_ENABLED,
    CONF_EV_PREFIX,
    CONF_SERVER_URL,
    EV_ENTITY_KEYS,
    REQUIRED_ENTITIES,
)
from ._base import SolarAcceleratorSensorBase


class SolarAcceleratorStatusSensor(SolarAcceleratorSensorBase):
    """Status połączenia z backendem (``connected``/``auth_error``/``error``/``disconnected``)."""

    _attr_icon = "mdi:cloud-check"
    _attr_translation_key = "connection_status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj sensor statusu połączenia."""
        super().__init__(hass, entry, coordinator_data, "connection_status")
        self._attr_name = "Status połączenia"

    @property
    def native_value(self) -> str:
        """Zwróć aktualny status połączenia."""
        return self.coordinator_data.get("connection_status", "unknown")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Dodatkowe pola: adres serwera i ostatnia odpowiedź (np. fragment błędu)."""
        return {
            "server_url": self.coordinator_data.get(CONF_SERVER_URL),
            "last_response": self.coordinator_data.get("last_response"),
        }


class SolarAcceleratorLastSentSensor(SolarAcceleratorSensorBase):
    """Znacznik czasu ostatniej udanej wysyłki paczki godzinowej."""

    _attr_icon = "mdi:clock-outline"
    _attr_translation_key = "last_sent"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj sensor ostatniej wysyłki."""
        super().__init__(hass, entry, coordinator_data, "last_sent")
        self._attr_name = "Ostatnie wysłanie"

    @property
    def native_value(self) -> str | None:
        """Zwróć czas ostatniej udanej wysyłki (None jeśli jeszcze nic nie wysłano)."""
        return self.coordinator_data.get("last_sent")


class SolarAcceleratorNextScheduledSensor(SolarAcceleratorSensorBase):
    """Znacznik czasu kolejnej zaplanowanej wysyłki (najbliższa pełna godzina)."""

    _attr_icon = "mdi:clock-fast"
    _attr_translation_key = "next_scheduled"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj sensor kolejnej wysyłki."""
        super().__init__(hass, entry, coordinator_data, "next_scheduled")
        self._attr_name = "Następne wysłanie"

    @property
    def native_value(self) -> str | None:
        """Zwróć czas planowanej kolejnej wysyłki."""
        return self.coordinator_data.get("next_scheduled")


class SolarAcceleratorEntitiesCountSensor(SolarAcceleratorSensorBase):
    """Liczba encji które miały stan przy ostatniej wysyłce + szczegółowa lista w atrybutach.

    Główna wartość to liczba, ale prawdziwa wartość siedzi w atrybutach — pokazują
    osobno listę zmapowanych encji falownika i ładowarki EV, w tym które mają stan,
    a które są brakujące/niedostępne. Pomaga zdiagnozować dlaczego serwer dostaje 0
    dla jakiegoś pola.
    """

    _attr_icon = "mdi:counter"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "entities_sent"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj sensor liczby encji."""
        super().__init__(hass, entry, coordinator_data, "entities_sent")
        self._attr_name = "Wysłane encje"

    @property
    def native_value(self) -> int:
        """Zwróć liczbę encji ze stanem z ostatniej wysyłki."""
        return self.coordinator_data.get("entities_sent", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Szczegóły wysyłanych encji z podziałem na falownik i ładowarkę.

        Każdą wymaganą encję klasyfikujemy do jednej z czterech grup:
        - falownik_lista  — zmapowana i ma stan,
        - falownik_brak   — niezmapowana lub stan unknown/unavailable,
        - ev_lista        — j.w. dla ładowarki EV (tylko gdy EV włączone),
        - ev_brak         — j.w.
        """
        entity_mapping = self.coordinator_data.get(CONF_ENTITY_MAPPING, {})
        ev_enabled = bool(
            self.coordinator_data.get(CONF_EV_ENABLED)
            and self.coordinator_data.get(CONF_EV_PREFIX)
        )

        inverter_entities: list[str] = []
        inverter_missing: list[str] = []
        ev_entities: list[str] = []
        ev_missing: list[str] = []

        ev_keys_set = set(EV_ENTITY_KEYS)

        for key, desc, unit, category in REQUIRED_ENTITIES:
            is_ev = key in ev_keys_set
            ha_id = entity_mapping.get(key)

            if is_ev:
                # Pomijamy encje EV jeśli użytkownik nie włączył ładowarki
                if not ev_enabled:
                    continue
                if ha_id:
                    state = self.hass.states.get(ha_id)
                    if state and state.state not in ("unknown", "unavailable"):
                        ev_entities.append(f"ev_charger.{key} → {ha_id}")
                    else:
                        ev_missing.append(f"ev_charger.{key} → {ha_id} (brak stanu)")
                else:
                    ev_missing.append(f"ev_charger.{key}")
            else:
                if ha_id:
                    state = self.hass.states.get(ha_id)
                    if state and state.state not in ("unknown", "unavailable"):
                        inverter_entities.append(f"inverter.{key} → {ha_id}")
                    else:
                        inverter_missing.append(f"inverter.{key} → {ha_id} (brak stanu)")
                else:
                    inverter_missing.append(f"inverter.{key}")

        attrs: dict[str, Any] = {
            "falownik_aktywne": len(inverter_entities),
            "falownik_brakujące": len(inverter_missing),
            "falownik_lista": inverter_entities,
            "falownik_brak": inverter_missing,
        }
        if ev_enabled:
            attrs["ev_aktywne"] = len(ev_entities)
            attrs["ev_brakujące"] = len(ev_missing)
            attrs["ev_lista"] = ev_entities
            attrs["ev_brak"] = ev_missing
            attrs["ev_prefix"] = self.coordinator_data.get(CONF_EV_PREFIX)
        else:
            attrs["ev_enabled"] = False

        return attrs
