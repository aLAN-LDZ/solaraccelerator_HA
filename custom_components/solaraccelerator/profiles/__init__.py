"""Rejestr profili źródeł danych.

Profile są pogrupowane w podfoldery wg źródła (``solarman/``, ``solarassistant/``,
``ocpp/``). Każdy plik modelu w takim folderze definiuje obiekt ``PROFILE``.

Dodanie nowego urządzenia = wrzucenie jednego pliku do właściwego folderu źródła
(nazwa pliku wg ``producent_model``). Rejestr wykrywa go automatycznie — nie trzeba
nic tu dopisywać. Dodanie nowego źródła = nowy podfolder + wpis w ``SOURCE_PACKAGES``
(kolejność = kolejność na liście wyboru w kreatorze).
"""
from __future__ import annotations

import importlib
import pkgutil

from ._base import Profile, ROLE_EV_CHARGER, ROLE_INVERTER, slugify_part

# Kolejność źródeł = kolejność profili na liście wyboru w kreatorze.
SOURCE_PACKAGES: tuple[str, ...] = ("solarman", "solarassistant", "ocpp")


def _discover() -> list[Profile]:
    """Zbierz obiekty ``PROFILE`` ze wszystkich plików modeli w podfolderach źródeł."""
    found: list[Profile] = []
    for source in SOURCE_PACKAGES:
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


__all__ = [
    "Profile",
    "ROLE_INVERTER",
    "ROLE_EV_CHARGER",
    "slugify_part",
    "SOURCE_PACKAGES",
    "PROFILES",
    "get_profile",
    "list_profiles",
]
