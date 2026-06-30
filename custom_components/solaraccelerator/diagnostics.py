"""Diagnostyka integracji — eksport profilu do zgłoszenia wsparcia.

Buduje bogaty snapshot (format: TODO/FORMAT_eksportu_profilu.md) — mapowanie odczytu i
sterowania wraz z metadanymi encji (domena, próbka stanu, jednostka, opcje selecta),
których nie da się odczytać poza instancją użytkownika. Użytkownik pobiera plik i przesyła
go do dodania oficjalnego wsparcia. Sekrety (klucz API) są redagowane.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration
from homeassistant.util import dt as dt_util

from . import inverters
from .const import (
    CONF_API_KEY,
    CONF_CONFIG_MODE,
    CONF_ENTITY_MAPPING,
    CONF_INVERTER_MANUFACTURER,
    CONF_INVERTER_MODEL,
    CONF_PROFILE_DRAFT,
    CONF_SOLARMAN_PREFIX,
    DOMAIN,
    EV_ENTITY_KEYS,
    INVERTER_KEYS,
)
from .profile_export import build_export, detect_prefix
from .profiles import get_profile

_REDACT = {CONF_API_KEY}


def _snapshot(hass: HomeAssistant, entity_id: str) -> dict[str, Any]:
    """Zbierz metadane encji z HA (tylko tu dostępne — na instancji użytkownika)."""
    domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
    state = hass.states.get(entity_id)
    if state is None:
        return {"domain": domain, "state": None, "unit": None, "options": None,
                "device_class": None, "friendly_name": None, "missing": True}
    attrs = state.attributes
    return {
        "domain": domain,
        "state": state.state,
        "unit": attrs.get("unit_of_measurement"),
        "options": attrs.get("options"),
        "device_class": attrs.get("device_class"),
        "friendly_name": attrs.get("friendly_name"),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Zwróć eksport profilu w formacie kontraktu + zredagowany surowy wpis."""
    draft: dict[str, Any] = dict(entry.options.get(CONF_PROFILE_DRAFT, {}))

    manufacturer = draft.get("manufacturer") or entry.data.get(CONF_INVERTER_MANUFACTURER) or ""
    model = draft.get("model") or entry.data.get(CONF_INVERTER_MODEL) or ""
    selected = get_profile(entry.data.get(CONF_CONFIG_MODE, ""))
    source = draft.get("source") or (selected.source if selected else "")

    entity_mapping: dict[str, str] = dict(entry.data.get(CONF_ENTITY_MAPPING, {}))
    role_keys = set(EV_ENTITY_KEYS) if source == "ocpp" else set(INVERTER_KEYS)
    read_mapping = {k: v for k, v in entity_mapping.items() if k in role_keys}

    control_mapping: dict[str, str] = dict(draft.get("control_mapping", {}))
    control_extra: list[str] = list(draft.get("control_extra", []))

    prefix = (
        draft.get("prefix")
        or entry.data.get(CONF_SOLARMAN_PREFIX)
        or detect_prefix(list(read_mapping.values()))
    )

    model_mod = inverters.resolve(manufacturer, model)
    canonical_type = model_mod.canonical_type if model_mod else (lambda knob: None)
    canonical_values = model_mod.canonical_values if model_mod else (lambda knob: None)

    integration = await async_get_integration(hass, DOMAIN)

    export = build_export(
        env={
            "format_version": 1,
            "generated_at": dt_util.utcnow().isoformat(),
            "integration_version": str(integration.version),
            "ha_version": HA_VERSION,
        },
        meta={
            "manufacturer": manufacturer,
            "model": model,
            "source": source,
            "prefix": prefix or "",
            "control_model": model_mod.MODEL_ID if model_mod else None,
        },
        capabilities=draft.get("capabilities", {}),
        read_mapping=read_mapping,
        control_mapping=control_mapping,
        control_extra=control_extra,
        notes=draft.get("notes", ""),
        get_snapshot=lambda eid: _snapshot(hass, eid),
        canonical_type=canonical_type,
        canonical_values=canonical_values,
    )

    return {
        "profile_export": export,
        "raw_entry": {
            "data": async_redact_data(dict(entry.data), _REDACT),
            "options": async_redact_data(dict(entry.options), _REDACT),
        },
    }
