"""Config flow for Solar Accelerator integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_SERVER_URL,
    CONF_SEND_INTERVAL,
    CONF_ENTITY_MAPPING,
    DEFAULT_SERVER_URL,
    DEFAULT_SEND_INTERVAL,
    API_PUSH_ENDPOINT,
    REQUIRED_ENTITIES,
    ENTITY_CATEGORIES,
)

_LOGGER = logging.getLogger(__name__)

# Group entities by category for multi-step flow
ENTITY_STEPS = ["pv", "battery", "inverter", "grid", "load", "temp"]


async def async_validate_api_key(
    hass: HomeAssistant,
    api_key: str,
    server_url: str,
) -> dict[str, Any]:
    """Validate API key by making a test request."""
    try:
        session = async_get_clientsession(hass)
        server_url = server_url.rstrip("/")
        endpoint = f"{server_url}{API_PUSH_ENDPOINT}"

        _LOGGER.debug("Validating API key at: %s", endpoint)

        # Send a minimal test request to validate the API key
        async with session.post(
            endpoint,
            json={
                "timestamp": "2000-01-01T00:00:00Z",
                "entities": {
                    "pv1_power": 0,
                },
            },
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            text = await resp.text()
            _LOGGER.debug("API response: status=%s, body=%s", resp.status, text[:200])

            if resp.status in (200, 201):
                return {"success": True}
            elif resp.status == 401:
                return {"success": False, "error": "invalid_api_key"}
            elif resp.status == 403:
                return {"success": False, "error": "invalid_api_key"}
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


def get_entities_for_category(category: str) -> list[tuple[str, str, str, str]]:
    """Get all entities for a specific category."""
    return [e for e in REQUIRED_ENTITIES if e[3] == category]


class SolarAcceleratorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solar Accelerator."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.api_key: str = ""
        self.server_url: str = DEFAULT_SERVER_URL
        self.send_interval: int = DEFAULT_SEND_INTERVAL
        self.entity_mapping: dict[str, str] = {}
        self.current_step_index: int = 0

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - API key validation."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY, "").strip()
            server_url = user_input.get(CONF_SERVER_URL, DEFAULT_SERVER_URL).strip()
            send_interval = user_input.get(CONF_SEND_INTERVAL, DEFAULT_SEND_INTERVAL)

            # Validate API key format
            if not api_key.startswith("sa_haapi_"):
                errors[CONF_API_KEY] = "invalid_api_key_format"
            elif len(api_key) < 40:
                errors[CONF_API_KEY] = "invalid_api_key_format"

            # Validate URL format
            if not server_url.startswith(("http://", "https://")):
                errors[CONF_SERVER_URL] = "invalid_url"

            # Validate interval
            if send_interval < 60:
                errors[CONF_SEND_INTERVAL] = "invalid_interval"

            if not errors:
                # Validate API key with server
                result = await async_validate_api_key(self.hass, api_key, server_url)

                if result["success"]:
                    self.api_key = api_key
                    self.server_url = server_url.rstrip("/")
                    self.send_interval = send_interval
                    self.current_step_index = 0
                    return await self.async_step_entities_pv()
                else:
                    errors["base"] = result.get("error", "cannot_connect")

        schema = vol.Schema({
            vol.Required(CONF_API_KEY): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_SERVER_URL, default=DEFAULT_SERVER_URL): TextSelector(
                TextSelectorConfig(type=TextSelectorType.URL)
            ),
            vol.Required(CONF_SEND_INTERVAL, default=DEFAULT_SEND_INTERVAL): NumberSelector(
                NumberSelectorConfig(min=60, max=3600, step=1, mode=NumberSelectorMode.BOX)
            ),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def _async_step_entities(
        self, category: str, next_step: str | None, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Generic handler for entity mapping steps."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Save mappings for this category
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
                    # All steps complete - create entry
                    return self._create_entry()

        # Build schema for this category
        category_entities = get_entities_for_category(category)
        schema_dict = {}

        for entity_key, description, unit, _ in category_entities:
            default_value = self.entity_mapping.get(entity_key, vol.UNDEFINED)
            field_label = f"{entity_key}"

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
        """Handle PV entity mapping."""
        return await self._async_step_entities("pv", "entities_battery", user_input)

    async def async_step_entities_battery(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle battery entity mapping."""
        return await self._async_step_entities("battery", "entities_inverter", user_input)

    async def async_step_entities_inverter(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle inverter entity mapping."""
        return await self._async_step_entities("inverter", "entities_grid", user_input)

    async def async_step_entities_grid(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle grid entity mapping."""
        return await self._async_step_entities("grid", "entities_load", user_input)

    async def async_step_entities_load(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle load entity mapping."""
        return await self._async_step_entities("load", "entities_temp", user_input)

    async def async_step_entities_temp(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle temperature entity mapping."""
        return await self._async_step_entities("temp", None, user_input)

    def _create_entry(self) -> FlowResult:
        """Create the config entry."""
        # Generate a unique ID based on API key prefix
        api_key_suffix = self.api_key[-8:] if len(self.api_key) >= 8 else self.api_key
        unique_id = f"solaraccelerator_{api_key_suffix}"

        return self.async_create_entry(
            title=f"SolarAccelerator",
            data={
                CONF_API_KEY: self.api_key,
                CONF_SERVER_URL: self.server_url,
                CONF_SEND_INTERVAL: self.send_interval,
                CONF_ENTITY_MAPPING: self.entity_mapping,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return SolarAcceleratorOptionsFlow()


class SolarAcceleratorOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Solar Accelerator."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            send_interval = user_input.get(CONF_SEND_INTERVAL, DEFAULT_SEND_INTERVAL)

            if send_interval < 60:
                errors[CONF_SEND_INTERVAL] = "invalid_interval"
            else:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_SEND_INTERVAL: send_interval,
                    },
                )

        current_interval = self.config_entry.options.get(
            CONF_SEND_INTERVAL,
            self.config_entry.data.get(CONF_SEND_INTERVAL, DEFAULT_SEND_INTERVAL),
        )

        schema = vol.Schema({
            vol.Required(CONF_SEND_INTERVAL, default=current_interval): NumberSelector(
                NumberSelectorConfig(min=60, max=3600, step=1, mode=NumberSelectorMode.BOX)
            ),
        })

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
