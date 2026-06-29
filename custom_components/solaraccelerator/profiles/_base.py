"""Definicja profilu źródła danych falownika/ładowarki.

Profil to deklaratywny słownik dla jednej kombinacji *producent × model × źródło*
(np. ten sam falownik Deye wystawiony przez Solarman ma inne nazwy encji niż przez
SolarAssistant — to dwa różne profile). Tak samo różne ładowarki to różne profile.
Profil opisuje, jak z podanego prefiksu zbudować mapowanie ``klucz_kanoniczny →
entity_id`` w Home Assistant.

Identyfikator profilu (``id``) jest liczony ze schematu ``producent_model_source``,
więc nazewnictwo jest spójne dla wszystkich urządzeń. W tej fazie profil niesie
wyłącznie warstwę ODCZYTU (``read_template``); pola pod sterowanie i normalizację
dojdą w kolejnych etapach.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# Role profili — falownik vs ładowarka EV. Decyduje, w którym kroku kreatora
# profil jest oferowany do wyboru.
ROLE_INVERTER = "inverter"
ROLE_EV_CHARGER = "ev_charger"


def slugify_part(value: str) -> str:
    """Sprowadź fragment nazwy do slugu (małe litery, znaki spoza [a-z0-9] → ``_``)."""
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


@dataclass(frozen=True)
class Profile:
    """Pojedynczy profil źródła danych.

    Pola:
    - ``manufacturer`` — producent urządzenia (np. ``Deye``, ``Autel``),
    - ``model``        — model urządzenia (np. ``SUN-12K-SG04LP3``, ``MaxiCharger``),
    - ``source``       — źródło encji w HA (np. ``solarman``, ``solarassistant``, ``ocpp``);
                         dla falownika jest to zarazem schemat nazw wysyłany w paczce danych,
    - ``label``        — etykieta pokazywana na liście wyboru w kreatorze,
    - ``role``         — ``inverter`` lub ``ev_charger``,
    - ``read_template``— szablon mapowania ``klucz_kanoniczny → "domain.{prefix}_suffix"``;
                         ``{prefix}`` jest podstawiany metodą ``build_mapping``,
    - ``prefix_example``— przykład prefiksu pokazywany w opisie kroku kreatora,
    - ``aliases``      — dawne identyfikatory profilu (zgodność wsteczna istniejących wpisów).

    ``id`` jest liczone automatycznie jako ``producent_model_source``.
    """

    manufacturer: str
    model: str
    source: str
    label: str
    role: str
    read_template: dict[str, str] = field(default_factory=dict)
    prefix_example: str = ""
    aliases: tuple[str, ...] = ()
    id: str = field(init=False)

    def __post_init__(self) -> None:
        computed = "_".join(
            slugify_part(part) for part in (self.manufacturer, self.model, self.source)
        )
        object.__setattr__(self, "id", computed)

    def build_mapping(self, prefix: str) -> dict[str, str]:
        """Zbuduj mapowanie ``klucz_kanoniczny → entity_id`` dla podanego prefiksu.

        Podstawia ``{prefix}`` w każdej wartości szablonu. Użytkownik może później
        ręcznie skorygować pojedyncze wpisy, jeśli któryś identyfikator nie pasuje.
        """
        return {key: tmpl.format(prefix=prefix) for key, tmpl in self.read_template.items()}
