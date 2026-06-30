"""Silnik kodeków wartości sterujących — tłumaczenie wartość kanoniczna ↔ encje HA.

Generyczny i niezależny od falownika. To samo logiczne ustawienie (np. „godzina startu
slotu TOU = 13:00") bywa w HA wystawione różnie zależnie od integracji:
- encja ``time`` ze stanem ``"13:00:00"``,
- encja ``number`` ze stanem ``1300`` (HH:MM) lub ``780`` (minuty),
- encja ``select`` z opcją ``"13:00"``.

Binding opisuje, JAK dany knob mapuje się na encję(e) + jaki kodek przelicza wartość.
``encode`` buduje komendy (``ServiceCall``) do wykonania, ``decode`` czyta stan encji z
powrotem do wartości kanonicznej (do weryfikacji/guarda).

Wartości kanoniczne:
- czas    — minuty od północy (``int`` 0..1439),
- liczba  — ``float``/``int`` w jednostce kanonicznej,
- enum    — ``str`` z kanonicznego zbioru (np. ``off``/``grid``/``gen``/``both``),
- bool    — ``True``/``False``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

# Komenda do wykonania na encji HA (zgodna z kształtem komend write_managera).
ServiceCall = dict[str, Any]

# Domeny encji obsługujące dane operacje (encja danej domeny → właściwa usługa HA).
_NUMBER_DOMAINS = {"number", "input_number"}
_OPTION_DOMAINS = {"select", "input_select"}
_BOOL_DOMAINS = {"switch", "input_boolean"}


# ── Bindingi ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Single:
    """Knob → jedna encja, przeliczana wskazanym kodekiem."""

    entity: str                                  # szablon z {prefix}
    codec: str                                   # nazwa kodeka (patrz niżej)
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FanoutTarget:
    entity: str                                  # szablon z {prefix}
    on_when: frozenset[str]                       # kanoniczne wartości enuma włączające tę encję


@dataclass(frozen=True)
class Fanout:
    """Knob (enum/bool) → wiele encji bool (np. tryb ładowania = grid_switch + gen_switch)."""

    targets: tuple[FanoutTarget, ...]


Binding = Single | Fanout


def binding_from_spec(spec: dict[str, Any]) -> Binding:
    """Zbuduj binding z deklaratywnego specu (z profilu / harvestu).

    Single: ``{"entity": "...", "codec": "number", "params": {...}}``.
    Fanout: ``{"fanout": [{"entity": "...", "on_when": ["grid", "both"]}, ...]}``.
    """
    if "fanout" in spec:
        return Fanout(tuple(
            FanoutTarget(t["entity"], frozenset(t["on_when"])) for t in spec["fanout"]
        ))
    return Single(spec["entity"], spec["codec"], spec.get("params", {}))


def encode_spec(spec: dict[str, Any], value: Any, prefix: str) -> list[ServiceCall]:
    """Wygodny wrapper: ``binding_from_spec`` + ``encode``."""
    return encode(binding_from_spec(spec), value, prefix)


def decode_spec(spec: dict[str, Any], get_state: Callable[[str], str | None], prefix: str) -> Any:
    """Wygodny wrapper: ``binding_from_spec`` + ``decode``."""
    return decode(binding_from_spec(spec), get_state, prefix)


# ── Pomocnicze: budowa ServiceCall wg domeny encji ──────────────────────────

def _domain(entity_id: str) -> str:
    return entity_id.split(".", 1)[0]


def _call(entity_id: str, domain: str, service: str, data: dict[str, Any]) -> ServiceCall:
    return {"domain": domain, "service": service, "entity_id": entity_id, "service_data": data}


def _set_number(entity_id: str, value: float) -> ServiceCall:
    return _call(entity_id, _domain(entity_id), "set_value", {"value": value})


def _set_option(entity_id: str, option: str) -> ServiceCall:
    return _call(entity_id, _domain(entity_id), "select_option", {"option": option})


def _set_bool(entity_id: str, on: bool) -> ServiceCall:
    return _call(entity_id, _domain(entity_id), "turn_on" if on else "turn_off", {})


def _set_time(entity_id: str, minutes: int) -> ServiceCall:
    """Ustaw godzinę — usługa i format zależą od domeny encji."""
    dom = _domain(entity_id)
    if dom in _OPTION_DOMAINS:                    # czas jako opcja selecta, np. "13:00"
        return _set_option(entity_id, _min_to_hm(minutes))
    if dom == "input_datetime":
        return _call(entity_id, "input_datetime", "set_datetime", {"time": _min_to_hms(minutes)})
    return _call(entity_id, "time", "set_value", {"time": _min_to_hms(minutes)})


# ── Konwersje czasu ─────────────────────────────────────────────────────────

def _min_to_hms(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h:02d}:{m:02d}:00"


def _min_to_hm(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h:02d}:{m:02d}"


def _parse_time_to_min(state: str) -> int | None:
    parts = str(state).strip().split(":")
    if len(parts) < 2:
        return None
    try:
        return int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        return None


# ── ENCODE: wartość kanoniczna → ServiceCall(e) ─────────────────────────────

def encode(binding: Binding, value: Any, prefix: str) -> list[ServiceCall]:
    """Zbuduj komendy ustawiające encję(e) na wartość kanoniczną."""
    if isinstance(binding, Fanout):
        out: list[ServiceCall] = []
        for target in binding.targets:
            out.append(_set_bool(target.entity.format(prefix=prefix), value in target.on_when))
        return out

    entity = binding.entity.format(prefix=prefix)
    codec = binding.codec
    if codec == "number":
        return [_set_number(entity, value)]
    if codec == "number_scaled":
        return [_set_number(entity, value * binding.params.get("factor", 1.0))]
    if codec == "time_iso":
        return [_set_time(entity, value)]
    if codec == "time_hhmm":
        h, m = divmod(int(value), 60)
        return [_set_number(entity, h * 100 + m)]
    if codec == "time_minutes":
        return [_set_number(entity, int(value))]
    if codec == "enum":
        return [_set_option(entity, binding.params["options"][value])]
    if codec == "bool_switch":
        return [_set_bool(entity, bool(value))]
    if codec == "bool_select":
        return [_set_option(entity, binding.params["on"] if value else binding.params["off"])]
    raise ValueError(f"Nieznany kodek: {codec}")


# ── DECODE: stan encji → wartość kanoniczna (do verify/guard) ───────────────

def decode(binding: Binding, get_state: Callable[[str], str | None], prefix: str) -> Any:
    """Odczytaj wartość kanoniczną ze stanu encji. ``None`` gdy się nie da."""
    if isinstance(binding, Fanout):
        on_targets = {
            t for t in binding.targets
            if _is_on(get_state(t.entity.format(prefix=prefix)))
        }
        # Dopasuj kanoniczną wartość, której wzorzec on/off pasuje do faktycznego stanu.
        candidates = set().union(*(t.on_when for t in binding.targets)) | {"off"}
        for candidate in candidates:
            expected = {t for t in binding.targets if candidate in t.on_when}
            if expected == on_targets:
                return candidate
        return None

    state = get_state(binding.entity.format(prefix=prefix))
    if state is None or state in ("unknown", "unavailable", ""):
        return None
    codec = binding.codec
    try:
        if codec == "number":
            return float(state)
        if codec == "number_scaled":
            return float(state) / binding.params.get("factor", 1.0)
        if codec == "time_iso":
            return _parse_time_to_min(state)
        if codec == "time_hhmm":
            v = int(float(state))
            return (v // 100) * 60 + (v % 100)
        if codec == "time_minutes":
            return int(float(state))
        if codec == "enum":
            reverse = {v: k for k, v in binding.params["options"].items()}
            return reverse.get(state)
        if codec == "bool_switch":
            return _is_on(state)
        if codec == "bool_select":
            return state == binding.params["on"]
    except (ValueError, TypeError, KeyError):
        return None
    raise ValueError(f"Nieznany kodek: {codec}")


def _is_on(state: str | None) -> bool:
    return str(state).lower() in ("on", "true", "1", "enabled")
