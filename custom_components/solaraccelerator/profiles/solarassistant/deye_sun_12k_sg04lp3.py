"""Profil: Deye SUN-12K-SG04LP3 wystawiony przez appliance SolarAssistant (MQTT).

SolarAssistant eksponuje encje w schemacie ``sensor.{prefix}_{pole}``, gdzie prefix
to slug głównego urządzenia falownika (np. ``deye_sunsynk_sol_ark_3_phase`` dla
``sensor.deye_sunsynk_sol_ark_3_phase_pv_power``). Liczniki energii (``*_energy_*``)
są dzienne (resetują się dobowo).

Pola bez odpowiednika w SolarAssistant są pominięte (nie trafiają do mapowania):
``total_pv_generation``, ``battery_soh``, ``inverter_current_l1/l2/l3``,
``inverter_power``, ``grid_connected_status``, ``dc_transformer_temp``.
"""
from __future__ import annotations

from .._base import Profile, ROLE_INVERTER

PROFILE = Profile(
    manufacturer="Deye",
    model="SUN-12K-SG04LP3",
    source="solarassistant",
    label="Deye SUN-12K-SG04LP3 — SolarAssistant (prefix, automatyczne mapowanie)",
    role=ROLE_INVERTER,
    prefix_example="np. deye_sunsynk_sol_ark_3_phase",
    aliases=("solarassistant",),
    read_template={
        # PV
        "day_pv_energy": "sensor.{prefix}_pv_energy",
        "pv1_power": "sensor.{prefix}_pv_power_1",
        "pv2_power": "sensor.{prefix}_pv_power_2",
        "pv1_voltage": "sensor.{prefix}_pv_voltage_1",
        "pv2_voltage": "sensor.{prefix}_pv_voltage_2",
        "pv1_current": "sensor.{prefix}_pv_current_1",
        "pv2_current": "sensor.{prefix}_pv_current_2",
        # Bateria
        "day_battery_discharge": "sensor.{prefix}_battery_energy_out",
        "day_battery_charge": "sensor.{prefix}_battery_energy_in",
        "battery_power": "sensor.{prefix}_battery_power",
        "battery_current": "sensor.{prefix}_battery_current",
        "battery_temp": "sensor.{prefix}_battery_temperature",
        "battery_voltage": "sensor.{prefix}_battery_voltage",
        "battery_soc": "sensor.{prefix}_battery_state_of_charge",
        # Inwerter
        "inverter_status": "sensor.{prefix}_device_mode",
        "inverter_voltage_l1": "sensor.{prefix}_grid_voltage_1",
        "inverter_voltage_l2": "sensor.{prefix}_grid_voltage_2",
        "inverter_voltage_l3": "sensor.{prefix}_grid_voltage_3",
        # Sieć
        "grid_power": "sensor.{prefix}_grid_power",
        "grid_ct_power_l1": "sensor.{prefix}_grid_power_1",
        "grid_ct_power_l2": "sensor.{prefix}_grid_power_2",
        "grid_ct_power_l3": "sensor.{prefix}_grid_power_3",
        "day_grid_import": "sensor.{prefix}_grid_energy_in",
        "day_grid_export": "sensor.{prefix}_grid_energy_out",
        # Obciążenie
        "day_load_energy": "sensor.{prefix}_load_energy",
        "load_power_l1": "sensor.{prefix}_load_power_1",
        "load_power_l2": "sensor.{prefix}_load_power_2",
        "load_power_l3": "sensor.{prefix}_load_power_3",
        "load_frequency": "sensor.{prefix}_grid_frequency",
        # Temperatury
        "radiator_temp": "sensor.{prefix}_temperature",
    },
)
