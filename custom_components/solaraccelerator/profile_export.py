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

import json
import re
from typing import Any, Callable


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


def parametrize_entity(entity_id: str, prefix: str) -> str:
    """Zamień pojedynczy entity_id na szablon z ``{prefix}`` (lub zostaw dosłowny)."""
    if not entity_id or "." not in entity_id:
        return entity_id
    domain, object_id = entity_id.split(".", 1)
    if prefix and object_id.startswith(prefix + "_"):
        return f"{domain}.{{prefix}}_{object_id[len(prefix) + 1:]}"
    return entity_id


def parametrize(mapping: dict[str, str], prefix: str) -> dict[str, str]:
    """Zamień entity_id na szablony z ``{prefix}`` tam, gdzie pasuje prefiks.

    Encje nie zaczynające się od ``{prefix}_`` zostają dosłowne (przypadek
    niejednolitego nazewnictwa — wymaga ręcznego przeglądu przy dodawaniu profilu).
    """
    return {key: parametrize_entity(entity_id, prefix) for key, entity_id in mapping.items()}


def _is_fanout(value: Any) -> bool:
    """Czy wartość sterująca to spec fan-out (knob → wiele encji), a nie pojedyncza encja."""
    return isinstance(value, dict) and "fanout" in value


def _value_template_entities(value: Any) -> list[str]:
    """Szablony encji wynikające z wartości sterującej (string → jeden, fan-out → wiele).

    Używane do wykrycia encji, których nie udało się sparametryzować prefiksem.
    """
    if _is_fanout(value):
        return [t.get("entity", "") for t in value["fanout"]]
    return [value or ""]


def parametrize_control_value(value: Any, prefix: str) -> Any:
    """Sparametryzuj wartość sterującą: pojedynczą encję (string) lub spec fan-out (dict).

    Dla fan-outu parametryzuje encję każdego celu, zachowując ``on_when``.
    """
    if _is_fanout(value):
        return {
            "fanout": [
                {**target, "entity": parametrize_entity(target.get("entity", ""), prefix)}
                for target in value["fanout"]
            ]
        }
    return parametrize_entity(value, prefix)


def parametrize_control(mapping: dict[str, Any], prefix: str) -> dict[str, Any]:
    """Sparametryzuj mapę sterowania (wartości: string lub spec fan-out)."""
    return {key: parametrize_control_value(value, prefix) for key, value in mapping.items()}


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
    control_template = parametrize_control(control_mapping, prefix)

    literal = sorted(
        key
        for key, value in {**read_template, **control_template}.items()
        if any("{prefix}" not in (entity or "") for entity in _value_template_entities(value))
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


def build_export(
    *,
    env: dict[str, Any],
    meta: dict[str, Any],
    capabilities: dict[str, bool],
    read_mapping: dict[str, str],
    control_mapping: dict[str, str],
    control_extra: list[str],
    notes: str,
    get_snapshot: Callable[[str], dict[str, Any]],
    canonical_type: Callable[[str], str | None],
    canonical_values: Callable[[str], list[str] | None],
) -> dict[str, Any]:
    """Złóż pełny eksport profilu w formacie kontraktu (patrz TODO/FORMAT_eksportu_profilu.md).

    Czyste — snapshoty encji i resolvery kanoniczne wstrzykiwane jako callable, żeby dało
    się testować bez Home Assistant.
    """
    prefix = meta.get("prefix", "")
    unparametrized: list[str] = []

    def make_entry(entity_raw: str, knob: str, with_canonical: bool) -> dict[str, Any]:
        template = parametrize_entity(entity_raw, prefix)
        if "{prefix}" not in template:
            unparametrized.append(knob)
        values = canonical_values(knob) if with_canonical else None
        return {
            "entity": template,
            "entity_raw": entity_raw,
            "canonical_type": canonical_type(knob) if with_canonical else None,
            "canonical_values": list(values) if values else None,
            "snapshot": get_snapshot(entity_raw),
        }

    def make_control_entry(knob: str, value: Any) -> dict[str, Any]:
        """Wpis sterowania: pojedyncza encja albo fan-out (knob → wiele encji bool)."""
        if not _is_fanout(value):
            return make_entry(value, knob, True)
        targets: list[dict[str, Any]] = []
        for target in value["fanout"]:
            entity_raw = target.get("entity", "")
            template = parametrize_entity(entity_raw, prefix)
            if "{prefix}" not in template:
                unparametrized.append(knob)
            targets.append({
                "entity": template,
                "entity_raw": entity_raw,
                "on_when": list(target.get("on_when", [])),
                "snapshot": get_snapshot(entity_raw),
            })
        values = canonical_values(knob)
        return {
            "entity": None,
            "fanout": targets,
            "canonical_type": canonical_type(knob),
            "canonical_values": list(values) if values else None,
        }

    read = {k: make_entry(v, k, False) for k, v in read_mapping.items() if v}
    control = {k: make_control_entry(k, v) for k, v in control_mapping.items() if v}
    extra = [
        {
            "entity": parametrize_entity(eid, prefix),
            "entity_raw": eid,
            "snapshot": get_snapshot(eid),
        }
        for eid in control_extra
        if eid
    ]

    profile_id = "_".join(_slug(p) for p in (meta["manufacturer"], meta["model"], meta["source"]))
    file_path = (
        f"profiles/{_slug(meta['source'])}/"
        f"{_slug(meta['manufacturer'])}_{_slug(meta['model'])}.py"
    )

    return {
        "format_version": env["format_version"],
        "generated_at": env["generated_at"],
        "integration_version": env["integration_version"],
        "ha_version": env["ha_version"],
        "device": {
            "manufacturer": meta["manufacturer"],
            "model": meta["model"],
            "source": meta["source"],
            "prefix": prefix,
            "control_model": meta.get("control_model"),
            "profile_id": profile_id,
            "file_path": file_path,
        },
        "capabilities": {k: bool(v) for k, v in capabilities.items() if v},
        "read": read,
        "control": control,
        "control_extra": extra,
        "unparametrized": sorted(set(unparametrized)),
        "notes": notes or "",
    }


def _render_control_value(value: Any) -> str:
    """Wyrenderuj wartość szablonu jako literał Pythona.

    Spec fan-out (dict) zawiera tylko stringi i listy stringów, więc ``json.dumps``
    daje poprawny składniowo literał Pythona (cudzysłowy podwójne, listy).
    """
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return f'"{value}"'


def _render_template_dict(name: str, mapping: dict[str, Any]) -> str:
    """Wyrenderuj słownik szablonu jako wcięty blok Pythona."""
    if not mapping:
        return f"    {name}={{}},"
    lines = [f"    {name}={{"]
    for key, value in mapping.items():
        lines.append(f'        "{key}": {_render_control_value(value)},')
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
