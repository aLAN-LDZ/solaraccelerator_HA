"""Profil: Deye SUN-12K-SG04LP3 wystawiony przez integrację Solarman (HACS).

Integracja Solarman używa konwencji nazw ``sensor.{prefix}_{pole}``. Prefix podaje
użytkownik (np. ``deye`` dla ``sensor.deye_pv1_power``).
"""
from __future__ import annotations

from .._base import Profile, ROLE_INVERTER

PROFILE = Profile(
    manufacturer="Deye",
    model="SUN-12K-SG04LP3",
    source="solarman",
    label="Deye SUN-12K-SG04LP3 — Solarman (prefix, automatyczne mapowanie)",
    role=ROLE_INVERTER,
    prefix_example="np. deye, solarman, inverter",
    aliases=("solarman",),
    read_template={
        # PV
        "day_pv_energy": "sensor.{prefix}_today_production",
        "pv1_power": "sensor.{prefix}_pv1_power",
        "pv2_power": "sensor.{prefix}_pv2_power",
        "pv1_voltage": "sensor.{prefix}_pv1_voltage",
        "pv2_voltage": "sensor.{prefix}_pv2_voltage",
        "pv1_current": "sensor.{prefix}_pv1_current",
        "pv2_current": "sensor.{prefix}_pv2_current",
        "total_pv_generation": "sensor.{prefix}_total_production",
        # Bateria
        "day_battery_discharge": "sensor.{prefix}_today_battery_discharge",
        "day_battery_charge": "sensor.{prefix}_today_battery_charge",
        "battery_power": "sensor.{prefix}_battery_power",
        "battery_current": "sensor.{prefix}_battery_current",
        "battery_temp": "sensor.{prefix}_battery_temperature",
        "battery_voltage": "sensor.{prefix}_battery_voltage",
        "battery_soc": "sensor.{prefix}_battery",
        "battery_soh": "sensor.{prefix}_battery_soh",
        # Inwerter
        "inverter_status": "sensor.{prefix}_device_relay",
        "inverter_voltage_l1": "sensor.{prefix}_grid_l1_voltage",
        "inverter_voltage_l2": "sensor.{prefix}_grid_l2_voltage",
        "inverter_voltage_l3": "sensor.{prefix}_grid_l3_voltage",
        "inverter_current_l1": "sensor.{prefix}_internal_ct1_current",
        "inverter_current_l2": "sensor.{prefix}_internal_ct2_current",
        "inverter_current_l3": "sensor.{prefix}_internal_ct3_current",
        "inverter_power": "sensor.{prefix}_internal_power",
        # Sieć
        "grid_power": "sensor.{prefix}_grid_power",
        "grid_ct_power_l1": "sensor.{prefix}_grid_l1_power",
        "grid_ct_power_l2": "sensor.{prefix}_grid_l2_power",
        "grid_ct_power_l3": "sensor.{prefix}_grid_l3_power",
        "day_grid_import": "sensor.{prefix}_today_energy_import",
        "day_grid_export": "sensor.{prefix}_today_energy_export",
        "grid_connected_status": "binary_sensor.{prefix}_grid",
        # Obciążenie
        "day_load_energy": "sensor.{prefix}_today_load_consumption",
        "load_power_l1": "sensor.{prefix}_load_l1_power",
        "load_power_l2": "sensor.{prefix}_load_l2_power",
        "load_power_l3": "sensor.{prefix}_load_l3_power",
        "load_frequency": "sensor.{prefix}_grid_frequency",
        # Temperatury
        "radiator_temp": "sensor.{prefix}_temperature",
        "dc_transformer_temp": "sensor.{prefix}_dc_temperature",
    },
)
