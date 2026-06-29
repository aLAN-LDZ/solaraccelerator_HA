"""Budowa szkicu profilu z ręcznej konfiguracji użytkownika (do zgłoszenia wsparcia).

Czyste funkcje (bez Home Assistant), żeby dało się je testować:
- ``detect_prefix``       — wykryj wspólny prefiks z listy zmapowanych encji,
- ``parametrize``         — zamień konkretne entity_id na szablon ``"...{prefix}..."``,
- ``build_profile_draft`` — złóż kompletny szkic profilu (meta + odczyt + sterowanie + capabilities),
- ``render_profile_py``   — wyrenderuj szkic jako zawartość pliku ``profiles/<źródło>/<model>.py``.

Szkic trafia do diagnostyki integracji — użytkownik pobiera go i przesyła do dodania
oficjalnego wsparcia.
"""
from __future__ import annotations

import re
from typing import Any


def _slug(value: str) -> str:
    """Slug fragmentu nazwy (małe litery, znaki spoza [a-z0-9] → ``_``).

    Spójne z ``profiles._base.slugify_part`` — trzymane lokalnie, żeby moduł nie miał
    zależności od pakietu profili (łatwiejsze testowanie).
    """
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def detect_prefix(entity_ids: list[str]) -> str:
    """Wykryj wspólny prefiks (tokeny rozdzielone ``_``) z object_id zmapowanych encji.

    Np. dla ``["sensor.mydeye_pv1_power", "sensor.mydeye_battery"]`` zwróci ``"mydeye"``.
    Zwraca pusty string, gdy nie ma wspólnego początku.
    """
    object_ids = [e.split(".", 1)[1] for e in entity_ids if "." in e]
    if not object_ids:
        return ""
    token_lists = [o.split("_") for o in object_ids]
    common: list[str] = []
    for tokens in zip(*token_lists):
        if len(set(tokens)) == 1:
            common.append(tokens[0])
        else:
            break
    return "_".join(common)


def parametrize(mapping: dict[str, str], prefix: str) -> dict[str, str]:
    """Zamień entity_id na szablony z ``{prefix}`` tam, gdzie pasuje prefiks.

    Encje nie zaczynające się od ``{prefix}_`` zostają dosłowne (przypadek
    niejednolitego nazewnictwa — wymaga ręcznego przeglądu przy dodawaniu profilu).
    """
    out: dict[str, str] = {}
    for key, entity_id in mapping.items():
        if not entity_id or "." not in entity_id:
            out[key] = entity_id
            continue
        domain, object_id = entity_id.split(".", 1)
        if prefix and object_id.startswith(prefix + "_"):
            out[key] = f"{domain}.{{prefix}}_{object_id[len(prefix) + 1:]}"
        else:
            out[key] = entity_id
    return out


def build_profile_draft(
    *,
    manufacturer: str,
    model: str,
    source: str,
    prefix: str,
    read_mapping: dict[str, str],
    control_mapping: dict[str, str],
    capabilities: dict[str, bool],
) -> dict[str, Any]:
    """Złóż kompletny szkic profilu gotowy do przeglądu i wklejenia do ``profiles/``.

    Dodatkowo wylicza pola pomocnicze dla osoby dodającej wsparcie:
    - ``literal_entities`` — encje, których nie udało się sparametryzować prefiksem
      (niejednolite nazewnictwo — do ręcznego sprawdzenia).
    """
    read_template = parametrize(read_mapping, prefix)
    control_template = parametrize(control_mapping, prefix)

    literal = sorted(
        key
        for key, value in {**read_template, **control_template}.items()
        if "{prefix}" not in (value or "")
    )

    profile_id = "_".join(_slug(p) for p in (manufacturer, model, source))

    return {
        "id": profile_id,
        "manufacturer": manufacturer,
        "model": model,
        "source": source,
        "prefix": prefix,
        "capabilities": {k: bool(v) for k, v in capabilities.items() if v},
        "read_template": read_template,
        "control_template": control_template,
        "literal_entities": literal,
        "file_path": f"profiles/{_slug(source)}/{_slug(manufacturer)}_{_slug(model)}.py",
    }


def _render_template_dict(name: str, mapping: dict[str, str]) -> str:
    """Wyrenderuj słownik szablonu jako wcięty blok Pythona."""
    if not mapping:
        return f"    {name}={{}},"
    lines = [f"    {name}={{"]
    for key, value in mapping.items():
        lines.append(f'        "{key}": "{value}",')
    lines.append("    },")
    return "\n".join(lines)


def render_profile_py(draft: dict[str, Any]) -> str:
    """Wyrenderuj szkic jako zawartość pliku profilu (do wklejenia do repo)."""
    role = "ROLE_EV_CHARGER" if draft["source"] == "ocpp" else "ROLE_INVERTER"
    caps = draft.get("capabilities") or {}
    caps_line = (
        "    capabilities={"
        + ", ".join(f'"{k}": True' for k in caps)
        + "},"
        if caps
        else "    capabilities={},"
    )
    parts = [
        '"""Profil wygenerowany z konfiguracji użytkownika — do przeglądu przed dodaniem."""',
        "from __future__ import annotations",
        "",
        f"from .._base import Profile, {role}",
        "",
        "PROFILE = Profile(",
        f'    manufacturer="{draft["manufacturer"]}",',
        f'    model="{draft["model"]}",',
        f'    source="{draft["source"]}",',
        f'    label="{draft["manufacturer"]} {draft["model"]} — {draft["source"]}",',
        f"    role={role},",
        caps_line,
        _render_template_dict("read_template", draft.get("read_template") or {}),
        _render_template_dict("control_template", draft.get("control_template") or {}),
        ")",
        "",
    ]
    return "\n".join(parts)
