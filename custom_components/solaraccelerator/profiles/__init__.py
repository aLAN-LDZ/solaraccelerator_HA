"""Rejestr profili źródeł danych.

Profile są pogrupowane w podfoldery wg źródła (``solarman/``, ``solarassistant/``,
``ocpp/``). Każdy plik modelu w takim folderze definiuje obiekt ``PROFILE``.

Dodanie nowego urządzenia = wrzucenie jednego pliku do właściwego folderu źródła
(nazwa pliku wg ``producent_model``). Rejestr wykrywa go automatycznie — nie trzeba
nic tu dopisywać. Dodanie nowego źródła = nowy podfolder + wpis w ``SOURCES``
(kolejność = kolejność na liście wyboru w kreatorze).
"""
from __future__ import annotations

import importlib
import pkgutil

from ._base import Profile, ROLE_EV_CHARGER, ROLE_INVERTER, slugify_part

# Źródła encji: slug folderu → czytelna nazwa pokazywana w kreatorze.
# Kolejność wyznacza kolejność na liście wyboru.
SOURCES: dict[str, str] = {
    "solarman": "Solarman",
    "solarassistant": "SolarAssistant",
    "ocpp": "OCPP",
}


def _discover() -> list[Profile]:
    """Zbierz obiekty ``PROFILE`` ze wszystkich plików modeli w podfolderach źródeł."""
    found: list[Profile] = []
    for source in SOURCES:
        package = importlib.import_module(f"{__name__}.{source}")
        module_names = sorted(m.name for m in pkgutil.iter_modules(package.__path__))
        for module_name in module_names:
            if module_name.startswith("_"):
                continue
            module = importlib.import_module(f"{__name__}.{source}.{module_name}")
            profile = getattr(module, "PROFILE", None)
            if isinstance(profile, Profile):
                found.append(profile)
    return found


PROFILES: list[Profile] = _discover()

# Indeks po id oraz po aliasach (dawne identyfikatory — zgodność wsteczna
# istniejących wpisów konfiguracji zapisanych przed wprowadzeniem schematu nazw).
_BY_ID: dict[str, Profile] = {}
for _p in PROFILES:
    _BY_ID[_p.id] = _p
    for _alias in _p.aliases:
        _BY_ID.setdefault(_alias, _p)


def get_profile(profile_id: str) -> Profile | None:
    """Zwróć profil o danym id (lub dawnym aliasie) albo ``None``, gdy nie istnieje."""
    return _BY_ID.get(profile_id)


def list_profiles(role: str) -> list[Profile]:
    """Zwróć profile danej roli (``inverter`` / ``ev_charger``) w kolejności rejestru."""
    return [p for p in PROFILES if p.role == role]


def list_sources(role: str) -> list[tuple[str, str]]:
    """Zwróć źródła mające ≥1 profil danej roli jako ``[(slug, label), ...]``.

    Kolejność wg ``SOURCES``. Używane do pierwszego kroku kreatora (wybór TYPU).
    """
    present = {p.source for p in list_profiles(role)}
    return [(slug, label) for slug, label in SOURCES.items() if slug in present]


def list_profiles_for_source(role: str, source: str) -> list[Profile]:
    """Zwróć profile danej roli należące do wskazanego źródła (do dropdownu modelu)."""
    return [p for p in PROFILES if p.role == role and p.source == source]


__all__ = [
    "Profile",
    "ROLE_INVERTER",
    "ROLE_EV_CHARGER",
    "slugify_part",
    "SOURCES",
    "PROFILES",
    "get_profile",
    "list_profiles",
    "list_sources",
    "list_profiles_for_source",
]
