"""Diagnostyka integracji — eksport szkicu profilu do zgłoszenia wsparcia.

Użytkownik, który ręcznie skonfigurował odczyt (i opcjonalnie sterowanie + capabilities
w kreatorze "Zgłoś / eksportuj profil"), pobiera tu gotowy szkic profilu i przesyła go
do dodania oficjalnego wsparcia. Sekrety (klucz API) są redagowane.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_API_KEY,
    CONF_CONFIG_MODE,
    CONF_ENTITY_MAPPING,
    CONF_PROFILE_DRAFT,
    CONF_SOLARMAN_PREFIX,
    EV_ENTITY_KEYS,
    INVERTER_KEYS,
)
from .profile_export import build_profile_draft, detect_prefix, render_profile_py
from .profiles import get_profile

_REDACT = {CONF_API_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Zwróć diagnostykę wpisu wraz z gotowym szkicem profilu (read + control + caps)."""
    entity_mapping: dict[str, str] = dict(entry.data.get(CONF_ENTITY_MAPPING, {}))
    draft_meta: dict[str, Any] = dict(entry.options.get(CONF_PROFILE_DRAFT, {}))

    # Źródło: z kreatora autoringu, a w razie braku — z profilu wybranego przy instalacji.
    config_mode = entry.data.get(CONF_CONFIG_MODE, "")
    selected = get_profile(config_mode)
    source = draft_meta.get("source") or (selected.source if selected else "")

    # Odczyt: tylko klucze właściwe dla roli (falownik vs ładowarka).
    role_keys = set(EV_ENTITY_KEYS) if source == "ocpp" else set(INVERTER_KEYS)
    read_mapping = {k: v for k, v in entity_mapping.items() if k in role_keys}

    control_mapping: dict[str, str] = dict(draft_meta.get("control_mapping", {}))

    # Prefiks: z kreatora → z instalacji → wykryty ze zmapowanych encji.
    prefix = (
        draft_meta.get("prefix")
        or entry.data.get(CONF_SOLARMAN_PREFIX)
        or detect_prefix(list(read_mapping.values()))
    )

    draft = build_profile_draft(
        manufacturer=draft_meta.get("manufacturer", ""),
        model=draft_meta.get("model", ""),
        source=source,
        prefix=prefix or "",
        read_mapping=read_mapping,
        control_mapping=control_mapping,
        capabilities=draft_meta.get("capabilities", {}),
    )

    return {
        "profile_draft": draft,
        "profile_py": render_profile_py(draft),
        "entry": {
            "data": async_redact_data(dict(entry.data), _REDACT),
            "options": async_redact_data(dict(entry.options), _REDACT),
        },
    }
