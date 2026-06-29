"""Profil: ładowarka Autel MaxiCharger wystawiona przez integrację OCPP (HACS).

Integracja OCPP tworzy encje w schemacie ``sensor.{prefix}_{pole}``, gdzie
``{prefix}`` to Charge Point ID (np. ``arccharger`` dla
``sensor.arccharger_power_active_import``).
"""
from __future__ import annotations

from .._base import Profile, ROLE_EV_CHARGER

PROFILE = Profile(
    manufacturer="Autel",
    model="MaxiCharger",
    source="ocpp",
    label="Prefix (automatyczne mapowanie)",
    role=ROLE_EV_CHARGER,
    prefix_example="np. arccharger, wallbox, chargepoint",
    aliases=("ocpp",),
    read_template={
        "status": "sensor.{prefix}_status",
        "status_connector": "sensor.{prefix}_status_connector",
        "vendor": "sensor.{prefix}_vendor",
        "power_active_import": "sensor.{prefix}_power_active_import",
        "energy_session": "sensor.{prefix}_energy_session",
        "energy_active_import_register": "sensor.{prefix}_energy_active_import_register",
        "current_import": "sensor.{prefix}_current_import",
        "voltage": "sensor.{prefix}_voltage",
        "time_session": "sensor.{prefix}_time_session",
        "error_code": "sensor.{prefix}_error_code",
        "transaction_id": "sensor.{prefix}_transaction_id",
    },
)
