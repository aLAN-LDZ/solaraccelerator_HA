"""Config flow integracji Solar Accelerator.

Kroki dodawania integracji:
1. ``user``                — klucz API + URL serwera (walidacja przez GET test-connection),
2. ``choose_mode``         — wybór modelu falownika i trybu (auto przez prefix / ręcznie),
3a. ``solarman_prefix``    — gdy tryb auto: prefix integracji Solarman,
3b. ``entities_pv/...``    — gdy tryb manualny: mapowanie encji w 6 ekranach (PV, bateria,
   inwerter, sieć, obciążenie, temperatury),
4. ``ev_charger``          — pytanie czy użytkownik ma ładowarkę EV,
5a-5c. analogicznie do kroków 2-3 dla ładowarki (jeśli włączona).

Stan między krokami trzymamy w polach klasy ``SolarAcceleratorConfigFlow``.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_SERVER_URL,
    CONF_ENTITY_MAPPING,
    CONF_CONFIG_MODE,
    CONF_SOLARMAN_PREFIX,
    CONF_EV_ENABLED,
    CONF_EV_PREFIX,
    CONF_EV_CONFIG_MODE,
    CONF_INVERTER_MODEL,
    CONF_EV_MODEL,
    CONFIG_MODE_SOLARMAN,
    CONFIG_MODE_MANUAL,
    DEFAULT_SERVER_URL,
    API_TEST_CONNECTION_ENDPOINT,
    REQUIRED_ENTITIES,
    ENTITY_CATEGORIES,
    SUPPORTED_INVERTERS,
    SUPPORTED_EV_CHARGERS,
    build_solarman_entity_mapping,
    build_ocpp_entity_mapping,
)

_LOGGER = logging.getLogger(__name__)


async def async_validate_api_key(
    hass: HomeAssistant,
    api_key: str,
    server_url: str,
) -> dict[str, Any]:
    """Sprawdź klucz API wysyłając GET na endpoint test-connection.

    Zwraca słownik z polem ``success`` (bool) oraz, w przypadku błędu, kodem
    ``error`` używanym przez UI do pokazania właściwego komunikatu:
    - ``invalid_api_key``    — HTTP 401 (zły klucz),
    - ``integration_disabled`` — HTTP 403 (integracja wyłączona po stronie serwera),
    - ``cannot_connect``     — błąd sieci lub timeout lub inny kod HTTP,
    - ``unknown``            — nieoczekiwany wyjątek.
    """
    try:
        session = async_get_clientsession(hass)
        server_url = server_url.rstrip("/")
        endpoint = f"{server_url}{API_TEST_CONNECTION_ENDPOINT}"

        _LOGGER.debug("Test połączenia: %s", endpoint)

        async with session.get(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
            },
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            text = await resp.text()
            _LOGGER.debug("Odpowiedź API: status=%s, body=%s", resp.status, text[:200])

            if resp.status == 200:
                return {"success": True}
            elif resp.status == 401:
                return {"success": False, "error": "invalid_api_key"}
            elif resp.status == 403:
                return {"success": False, "error": "integration_disabled"}
            else:
                _LOGGER.error("Walidacja API nieudana: %s - %s", resp.status, text)
                return {"success": False, "error": "cannot_connect"}
    except aiohttp.ClientConnectorError as e:
        _LOGGER.error("Błąd połączenia z %s: %s", server_url, e)
        return {"success": False, "error": "cannot_connect"}
    except aiohttp.ClientError as e:
        _LOGGER.error("Błąd klienta HTTP: %s", e)
        return {"success": False, "error": "cannot_connect"}
    except asyncio.TimeoutError:
        _LOGGER.error("Timeout połączenia z %s", server_url)
        return {"success": False, "error": "cannot_connect"}
    except Exception as e:
        _LOGGER.exception("Walidacja API nieudana: %s", e)
        return {"success": False, "error": "unknown"}


def get_entities_for_category(category: str) -> list[tuple[str, str, str, str]]:
    """Zwróć wszystkie wymagane encje należące do danej kategorii (pv/battery/...)."""
    return [e for e in REQUIRED_ENTITIES if e[3] == category]


class SolarAcceleratorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Obsługa config flow Solar Accelerator — krokowy kreator dodawania integracji."""

    VERSION = 1

    def __init__(self) -> None:
        """Zainicjalizuj puste pola — zostaną wypełnione w kolejnych krokach kreatora."""
        self.api_key: str = ""
        self.server_url: str = DEFAULT_SERVER_URL
        self.config_mode: str = ""
        self.solarman_prefix: str = ""
        self.inverter_model: str = ""
        self.ev_enabled: bool = False
        self.ev_config_mode: str = ""
        self.ev_prefix: str = ""
        self.ev_model: str = ""
        self.entity_mapping: dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Pierwszy krok — pobranie i walidacja klucza API + URL serwera."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY, "").strip()
            server_url = user_input.get(CONF_SERVER_URL, DEFAULT_SERVER_URL).strip()

            # Walidacja formatu klucza — musi zaczynać się od "sa_haapi_" i mieć min. 40 znaków
            if not api_key.startswith("sa_haapi_"):
                errors[CONF_API_KEY] = "invalid_api_key_format"
            elif len(api_key) < 40:
                errors[CONF_API_KEY] = "invalid_api_key_format"

            # Walidacja formatu URL — wymagamy schematu http/https
            if not server_url.startswith(("http://", "https://")):
                errors[CONF_SERVER_URL] = "invalid_url"

            if not errors:
                # Sprawdzenie klucza po stronie serwera (GET na test-connection)
                result = await async_validate_api_key(self.hass, api_key, server_url)

                if result["success"]:
                    self.api_key = api_key
                    self.server_url = server_url.rstrip("/")
                    return await self.async_step_choose_mode()
                else:
                    errors["base"] = result.get("error", "cannot_connect")

        schema = vol.Schema({
            vol.Required(CONF_API_KEY): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_SERVER_URL, default=DEFAULT_SERVER_URL): TextSelector(
                TextSelectorConfig(type=TextSelectorType.URL)
            ),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_choose_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Wybór modelu falownika oraz trybu konfiguracji (Solarman prefix vs ręczne mapowanie)."""
        if user_input is not None:
            self.config_mode = user_input.get(CONF_CONFIG_MODE, CONFIG_MODE_MANUAL)
            self.inverter_model = user_input.get(CONF_INVERTER_MODEL, "")

            if self.config_mode == CONFIG_MODE_SOLARMAN:
                return await self.async_step_solarman_prefix()
            else:
                return await self.async_step_entities_pv()

        schema = vol.Schema({
            vol.Required(CONF_INVERTER_MODEL): SelectSelector(
                SelectSelectorConfig(
                    options=SUPPORTED_INVERTERS,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(CONF_CONFIG_MODE, default=CONFIG_MODE_SOLARMAN): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": CONFIG_MODE_SOLARMAN, "label": "Prefix (automatyczne mapowanie)"},
                        {"value": CONFIG_MODE_MANUAL, "label": "Ręczne mapowanie encji"},
                    ],
                    mode=SelectSelectorMode.LIST,
                )
            ),
        })

        return self.async_show_form(
            step_id="choose_mode",
            data_schema=schema,
        )

    async def async_step_solarman_prefix(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Pobierz prefix integracji Solarman i zbuduj domyślne mapowanie encji."""
        errors: dict[str, str] = {}

        if user_input is not None:
            prefix = user_input.get(CONF_SOLARMAN_PREFIX, "").strip().lower()

            if not prefix:
                errors[CONF_SOLARMAN_PREFIX] = "prefix_required"
            elif " " in prefix or not prefix.replace("_", "").isalnum():
                errors[CONF_SOLARMAN_PREFIX] = "invalid_prefix"
            else:
                self.solarman_prefix = prefix
                self.entity_mapping = build_solarman_entity_mapping(prefix)
                return await self.async_step_ev_charger()

        schema = vol.Schema({
            vol.Required(CONF_SOLARMAN_PREFIX): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            ),
        })

        return self.async_show_form(
            step_id="solarman_prefix",
            data_schema=schema,
            errors=errors,
        )

    async def _async_step_entities(
        self, category: str, next_step: str | None, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Wspólna obsługa kroków mapowania encji.

        Dla każdej kategorii (pv, battery, inverter, grid, load, temp, ev_charger) pokazuje
        formularz z polami EntitySelector — po jednym dla każdej wymaganej encji w kategorii.
        Po zatwierdzeniu zapisuje mapowanie w ``self.entity_mapping`` i przechodzi do
        ``next_step`` (lub kończy kreator gdy ``next_step is None``).
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            category_entities = get_entities_for_category(category)
            all_filled = True

            for entity_key, _, _, _ in category_entities:
                mapped_entity = user_input.get(entity_key, "")
                if mapped_entity:
                    self.entity_mapping[entity_key] = mapped_entity
                else:
                    all_filled = False
                    errors[entity_key] = "entity_required"

            if all_filled:
                if next_step:
                    return await getattr(self, f"async_step_{next_step}")()
                else:
                    return self._create_entry()

        category_entities = get_entities_for_category(category)
        schema_dict = {}

        for entity_key, description, unit, _ in category_entities:
            default_value = self.entity_mapping.get(entity_key, vol.UNDEFINED)
            schema_dict[vol.Required(entity_key, default=default_value)] = EntitySelector(
                EntitySelectorConfig(domain=["sensor", "binary_sensor"])
            )

        return self.async_show_form(
            step_id=f"entities_{category}",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={
                "category_name": ENTITY_CATEGORIES.get(category, category),
            },
        )

    async def async_step_entities_pv(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Mapowanie encji PV (panele fotowoltaiczne)."""
        return await self._async_step_entities("pv", "entities_battery", user_input)

    async def async_step_entities_battery(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Mapowanie encji baterii."""
        return await self._async_step_entities("battery", "entities_inverter", user_input)

    async def async_step_entities_inverter(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Mapowanie encji inwertera."""
        return await self._async_step_entities("inverter", "entities_grid", user_input)

    async def async_step_entities_grid(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Mapowanie encji sieci elektroenergetycznej."""
        return await self._async_step_entities("grid", "entities_load", user_input)

    async def async_step_entities_load(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Mapowanie encji obciążenia (zużycia domowego)."""
        return await self._async_step_entities("load", "entities_temp", user_input)

    async def async_step_entities_temp(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Mapowanie encji temperatur (radiator, transformator DC)."""
        return await self._async_step_entities("temp", "ev_charger", user_input)

    async def async_step_ev_charger(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Pytanie czy użytkownik ma ładowarkę EV obsługiwaną przez integrację OCPP."""
        if user_input is not None:
            self.ev_enabled = bool(user_input.get(CONF_EV_ENABLED, False))

            if self.ev_enabled:
                return await self.async_step_ev_choose_mode()
            else:
                return self._create_entry()

        schema = vol.Schema({
            vol.Required(CONF_EV_ENABLED, default=False): bool,
        })

        return self.async_show_form(
            step_id="ev_charger",
            data_schema=schema,
        )

    async def async_step_ev_choose_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Wybór modelu ładowarki EV i trybu konfiguracji (prefix OCPP vs ręcznie)."""
        if user_input is not None:
            self.ev_model = user_input.get(CONF_EV_MODEL, "")
            self.ev_config_mode = user_input.get(CONF_EV_CONFIG_MODE, CONFIG_MODE_MANUAL)

            if self.ev_config_mode == CONFIG_MODE_SOLARMAN:
                return await self.async_step_ev_prefix()
            else:
                return await self.async_step_entities_ev_charger()

        schema = vol.Schema({
            vol.Required(CONF_EV_MODEL, default=SUPPORTED_EV_CHARGERS[0]["value"]): SelectSelector(
                SelectSelectorConfig(
                    options=SUPPORTED_EV_CHARGERS,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(CONF_EV_CONFIG_MODE, default=CONFIG_MODE_SOLARMAN): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": CONFIG_MODE_SOLARMAN, "label": "Prefix (automatyczne mapowanie)"},
                        {"value": CONFIG_MODE_MANUAL, "label": "Ręczne mapowanie encji"},
                    ],
                    mode=SelectSelectorMode.LIST,
                )
            ),
        })

        return self.async_show_form(
            step_id="ev_choose_mode",
            data_schema=schema,
        )

    async def async_step_ev_prefix(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Pobierz prefix OCPP (Charge Point ID) i zbuduj mapowanie encji ładowarki."""
        errors: dict[str, str] = {}

        if user_input is not None:
            prefix = user_input.get(CONF_EV_PREFIX, "").strip().lower()

            if not prefix:
                errors[CONF_EV_PREFIX] = "prefix_required"
            elif " " in prefix or not prefix.replace("_", "").isalnum():
                errors[CONF_EV_PREFIX] = "invalid_prefix"
            else:
                self.ev_prefix = prefix
                self.entity_mapping.update(build_ocpp_entity_mapping(prefix))
                return self._create_entry()

        schema = vol.Schema({
            vol.Required(CONF_EV_PREFIX): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            ),
        })

        return self.async_show_form(
            step_id="ev_prefix",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_entities_ev_charger(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ręczne mapowanie encji ładowarki EV (gdy użytkownik nie chce trybu prefix)."""
        return await self._async_step_entities("ev_charger", None, user_input)

    def _create_entry(self) -> FlowResult:
        """Zapisz finalny wpis konfiguracji — wszystkie zebrane wartości w jednym entry.data."""
        title = "Solar Accelerator"
        if self.config_mode == CONFIG_MODE_SOLARMAN:
            title = f"Solar Accelerator ({self.solarman_prefix})"

        return self.async_create_entry(
            title=title,
            data={
                CONF_API_KEY: self.api_key,
                CONF_SERVER_URL: self.server_url,
                CONF_CONFIG_MODE: self.config_mode,
                CONF_SOLARMAN_PREFIX: self.solarman_prefix,
                CONF_INVERTER_MODEL: self.inverter_model,
                CONF_EV_ENABLED: self.ev_enabled,
                CONF_EV_CONFIG_MODE: self.ev_config_mode,
                CONF_EV_PREFIX: self.ev_prefix,
                CONF_EV_MODEL: self.ev_model,
                CONF_ENTITY_MAPPING: self.entity_mapping,
            },
        )
