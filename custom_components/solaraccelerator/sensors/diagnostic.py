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

# Pusta diagnostyka — gdy write_manager jeszcze nie miał żadnego batcha
_EMPTY_WRITE_STATS: dict[str, Any] = {
    "entities": {},
    "last_batch_at": None,
    "last_batch_size": 0,
    "last_batch_acked": 0,
    "last_batch_failed": 0,
    "last_batch_retried": 0,
}


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


class SolarAcceleratorWriteStatsSensor(SolarAcceleratorSensorBase):
    """Diagnostyka write_managera — retry i finalny status per sterowana encja.

    Main state = liczba komend z ostatniego batcha które wymagały retry (0 = OK).
    Atrybuty zawierają meta ostatniego batcha + kumulatywne statystyki per entity_id
    od startu integracji: ile razy komenda dla danej encji się powiodła, ile razy
    musieliśmy retry'ować, jaka była ostatnia żądana wartość i finalny status.

    Sensor odświeża się natychmiast po każdym batchu — WriteManager woła
    ``coordinator_data['write_stats_notify']`` zaraz po ACK'owaniu komend.
    """

    _attr_icon = "mdi:reload-alert"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "write_stats"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator_data: dict[str, Any]
    ) -> None:
        """Zainicjalizuj sensor diagnostyki write_managera."""
        super().__init__(hass, entry, coordinator_data, "write_stats")
        self._attr_name = "Diagnostyka komend"

    async def async_added_to_hass(self) -> None:
        """Po dodaniu do HA zarejestruj notifier — write_manager woła go po każdym batchu."""
        await super().async_added_to_hass()
        # Schedule_update_ha_state można wołać synchronicznie z dowolnego kontekstu
        self.coordinator_data["write_stats_notify"] = self.async_schedule_update_ha_state

    async def async_will_remove_from_hass(self) -> None:
        """Wyczyść notifier — uniknij wołania callbacka po unmount."""
        if self.coordinator_data.get("write_stats_notify") == self.async_schedule_update_ha_state:
            self.coordinator_data.pop("write_stats_notify", None)
        await super().async_will_remove_from_hass()

    @property
    def native_value(self) -> int:
        """Liczba komend z ostatniego batcha które wymagały co najmniej 1 retry."""
        stats = self.coordinator_data.get("write_stats") or _EMPTY_WRITE_STATS
        return int(stats.get("last_batch_retried", 0))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Pełna diagnostyka batcha + kumulatywne statystyki per entity."""
        stats = self.coordinator_data.get("write_stats") or _EMPTY_WRITE_STATS
        return {
            "last_batch_at": stats.get("last_batch_at"),
            "last_batch_size": stats.get("last_batch_size", 0),
            "last_batch_acked": stats.get("last_batch_acked", 0),
            "last_batch_failed": stats.get("last_batch_failed", 0),
            "last_batch_retried": stats.get("last_batch_retried", 0),
            "entities": stats.get("entities", {}),
        }
