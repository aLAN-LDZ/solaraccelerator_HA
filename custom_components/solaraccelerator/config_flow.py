"""Config flow for Solar Accelerator integration."""
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
    CONFIG_MODE_SOLARMAN,
    CONFIG_MODE_MANUAL,
    DEFAULT_SERVER_URL,
    API_TEST_CONNECTION_ENDPOINT,
    REQUIRED_ENTITIES,
    OPTIONAL_ENTITIES,
    ENTITY_CATEGORIES,
    build_solarman_entity_mapping,
    Entity,
)

_LOGGER = logging.getLogger(__name__)


async def async_validate_api_key(
    hass: HomeAssistant,
    api_key: str,
    server_url: str,
) -> dict[str, Any]:
    """Validate API key by making a connection test request (GET)."""
    try:
        session = async_get_clientsession(hass)
        server_url = server_url.rstrip("/")
        endpoint = f"{server_url}{API_TEST_CONNECTION_ENDPOINT}"

        _LOGGER.debug("Testing connection at: %s", endpoint)

        async with session.get(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
            },
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            text = await resp.text()
            _LOGGER.debug("API response: status=%s, body=%s", resp.status, text[:200])

            if resp.status == 200:
                return {"success": True}
            elif resp.status == 401:
                return {"success": False, "error": "invalid_api_key"}
            elif resp.status == 403:
                return {"success": False, "error": "integration_disabled"}
            else:
                _LOGGER.error("API validation failed: %s - %s", resp.status, text)
                return {"success": False, "error": "cannot_connect"}
    except aiohttp.ClientConnectorError as e:
        _LOGGER.error("Connection error to %s: %s", server_url, e)
        return {"success": False, "error": "cannot_connect"}
    except aiohttp.ClientError as e:
        _LOGGER.error("Client error: %s", e)
        return {"success": False, "error": "cannot_connect"}
    except asyncio.TimeoutError:
        _LOGGER.error("Connection timeout to %s", server_url)
        return {"success": False, "error": "cannot_connect"}
    except Exception as e:
        _LOGGER.exception("API validation failed: %s", e)
        return {"success": False, "error": "unknown"}


def get_entities_for_category(category: str) -> list[Entity]:
    """Get all entities for a specific category."""
    return [e for e in REQUIRED_ENTITIES if e.category == category]


def get_optional_entities_for_category(category: str) -> list[Entity]:
    """Get optional entities for a specific category."""
    return [e for e in OPTIONAL_ENTITIES if e.category == category]


async def validate_entity_exists(hass: HomeAssistant, entity_id: str) -> bool:
    """Check if an entity exists in Home Assistant."""
    return hass.states.get(entity_id) is not None


async def validate_entity_unit(hass: HomeAssistant, entity_id: str, expected_unit: str) -> bool:
    """Check if an entity has the expected unit of measurement."""
    state = hass.states.get(entity_id)
    if state and state.attributes.get("unit_of_measurement") == expected_unit:
        return True
    return False


class SolarAcceleratorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solar Accelerator."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.api_key: str = ""
        self.server_url: str = DEFAULT_SERVER_URL
        self.config_mode: str = ""
        self.solarman_prefix: str = ""
        self.entity_mapping: dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - API key validation."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY, "").strip()
            server_url = user_input.get(CONF_SERVER_URL, DEFAULT_SERVER_URL).strip()

            # Validate API key format
            if not api_key.startswith("sa_haapi_"):
                errors[CONF_API_KEY] = "invalid_api_key_format"
            elif len(api_key) < 40:
                errors[CONF_API_KEY] = "invalid_api_key_format"

            # Validate URL format
            if not server_url.startswith(("http://", "https://")):
                errors[CONF_SERVER_URL] = "invalid_url"

            if not errors:
                # Validate API key with server
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
        """Handle configuration mode selection."""
        if user_input is not None:
            self.config_mode = user_input.get(CONF_CONFIG_MODE, CONFIG_MODE_MANUAL)

            if self.config_mode == CONFIG_MODE_SOLARMAN:
                return await self.async_step_solarman_prefix()
            else:
                return await self.async_step_entities_pv()

        schema = vol.Schema({
            vol.Required(CONF_CONFIG_MODE, default=CONFIG_MODE_SOLARMAN): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": CONFIG_MODE_SOLARMAN, "label": "Solarman (automatyczne mapowanie)"},
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
        """Handle Solarman prefix input."""
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
                return self._create_entry()

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
        """Generic handler for entity mapping steps."""
        errors: dict[str, str] = {}

        if user_input is not None:
            category_entities = get_entities_for_category(category)
            all_filled = True

            for entity in category_entities:
                mapped_entity = user_input.get(entity.key, "")
                if mapped_entity:
                    self.entity_mapping[entity.key] = mapped_entity
                else:
                    all_filled = False
                    errors[entity.key] = "entity_required"

            if all_filled:
                if next_step:
                    return await getattr(self, f"async_step_{next_step}")()
                else:
                    return self._create_entry()

        category_entities = get_entities_for_category(category)
        schema_dict = {}

        for entity in category_entities:
            default_value = self.entity_mapping.get(entity.key, vol.UNDEFINED)
            schema_dict[vol.Required(entity.key, default=default_value)] = EntitySelector(
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

    async def _async_step_optional_entities(
        self, category: str, next_step: str | None, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Generic handler for optional entity mapping steps."""
        errors: dict[str, str] = {}

        if user_input is not None:
            category_entities = get_optional_entities_for_category(category)

            for entity in category_entities:
                mapped_entity = user_input.get(entity.key, "").strip()
                if mapped_entity:
                    # Validate that the entity exists
                    if not await validate_entity_exists(self.hass, mapped_entity):
                        errors[entity.key] = "entity_not_found"
                    # Validate unit of measurement
                    elif not await validate_entity_unit(self.hass, mapped_entity, entity.unit):
                        errors[entity.key] = "invalid_unit"
                    else:
                        self.entity_mapping[entity.key] = mapped_entity

            # No errors, proceed to next step
            if not errors:
                if next_step:
                    return await getattr(self, f"async_step_{next_step}")()
                else:
                    return self._create_entry()

        category_entities = get_optional_entities_for_category(category)
        schema_dict = {}

        for entity in category_entities:
            default_value = self.entity_mapping.get(entity.key, vol.UNDEFINED)
            schema_dict[vol.Optional(entity.key, default=default_value)] = EntitySelector(
                EntitySelectorConfig(domain=["sensor", "binary_sensor"])
            )

        return self.async_show_form(
            step_id=f"entities_{category}_optional",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={
                "category_name": ENTITY_CATEGORIES.get(category, category),
            },
        )

    async def async_step_entities_pv(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle PV entity mapping."""
        return await self._async_step_entities("pv", "entities_pv_optional", user_input)

    async def async_step_entities_pv_optional(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle optional PV entity mapping."""
        return await self._async_step_optional_entities("pv", "entities_battery", user_input)

    async def async_step_entities_battery(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle battery entity mapping."""
        return await self._async_step_entities("battery", "entities_inverter", user_input)

    async def async_step_entities_inverter(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle inverter entity mapping."""
        return await self._async_step_entities("inverter", "entities_inverter_optional", user_input)

    async def async_step_entities_inverter_optional(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle optional inverter entity mapping."""
        return await self._async_step_optional_entities("inverter", "entities_grid", user_input)

    async def async_step_entities_grid(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle grid entity mapping."""
        return await self._async_step_entities("grid", "entities_grid_optional", user_input)

    async def async_step_entities_grid_optional(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle optional grid entity mapping."""
        return await self._async_step_optional_entities("grid", "entities_load", user_input)

    async def async_step_entities_load(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle load entity mapping."""
        return await self._async_step_entities("load", "entities_load_optional", user_input)

    async def async_step_entities_load_optional(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle optional load entity mapping."""
        return await self._async_step_optional_entities("load", "entities_temp", user_input)

    async def async_step_entities_temp(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle temperature entity mapping."""
        return await self._async_step_entities("temp", None, user_input)

    def _create_entry(self) -> FlowResult:
        """Create the config entry."""
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
                CONF_ENTITY_MAPPING: self.entity_mapping,
            },
        )
