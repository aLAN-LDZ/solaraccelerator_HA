"""Kanoniczne modele sterowania per rodzina falownika.

Model = zestaw knobów + ich kanoniczna semantyka (typy, zbiory opcji enumów). Wspólny
dla wszystkich źródeł danego falownika. Profile (źródło×falownik) mapują knoby na encje
przez bindingi, a silnik ``control_codecs`` przelicza wartości.

Dodanie nowej rodziny falownika = nowy moduł tutaj (np. ``sofar_setpoint.py``) — silnik
kodeków i mapowania źródeł pozostają bez zmian.
"""
from __future__ import annotations

from . import deye_hybrid

MODELS = {
    deye_hybrid.MODEL_ID: deye_hybrid,
}


def resolve(manufacturer: str, model: str):
    """Zwróć moduł kanonicznego modelu dla danego falownika (lub ``None``).

    Na razie jedna rodzina (Deye hybrydowe). Dołożenie kolejnej = rozszerzenie tej mapy.
    """
    if (manufacturer or "").strip().lower() == "deye":
        return deye_hybrid
    return None


__all__ = ["MODELS", "deye_hybrid", "resolve"]
