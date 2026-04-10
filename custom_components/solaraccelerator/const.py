"""Constants for the Solar Accelerator integration."""

from typing import NamedTuple


class Entity(NamedTuple):
    """Entity definition for SolarAccelerator."""
    key: str
    description: str
    unit: str
    category: str


DOMAIN = "solaraccelerator"

# Config flow
CONF_API_KEY = "api_key"
CONF_SERVER_URL = "server_url"
CONF_ENTITY_MAPPING = "entity_mapping"
CONF_CONFIG_MODE = "config_mode"
CONF_SOLARMAN_PREFIX = "solarman_prefix"

# Configuration modes
CONFIG_MODE_SOLARMAN = "solarman"
CONFIG_MODE_MANUAL = "manual"

# Default values
DEFAULT_SERVER_URL = "https://solaraccelerator.cloud"

# Sensor attributes
ATTR_LAST_SENT = "last_sent"
ATTR_LAST_RECEIVED = "last_received"
ATTR_CONNECTION_STATUS = "connection_status"
ATTR_ENTITIES_COUNT = "entities_count"
ATTR_NEXT_SCHEDULED = "next_scheduled"

# API endpoints
API_TEST_CONNECTION_ENDPOINT = "/api/homeassistant/test-connection"
API_SEND_DATA_ENDPOINT = "/api/homeassistant/send-data"
API_LIVE_ENDPOINT = "/api/homeassistant/live"
API_DATA_READY_ENDPOINT = "/api/homeassistant/data-ready"
API_PRICES_ENDPOINT = "/api/homeassistant/prices"
API_PROFIT_ENDPOINT = "/api/homeassistant/profit"

# Live channel defaults
DEFAULT_LIVE_INTERVAL = 15  # seconds — used until server tells us the real interval
LIVE_DISABLED_RETRY = 60    # seconds to wait when server returns 503
LIVE_AUTH_RETRY = 300       # seconds to wait after auth failure

# Required entities for SolarAccelerator API (always needed)
REQUIRED_ENTITIES = [
    # PV (Photovoltaic panels) - basic
    Entity("day_pv_energy", "Daily PV production", "kWh", "pv"),
    Entity("pv1_power", "PV string 1 power", "W", "pv"),
    Entity("pv1_voltage", "PV string 1 voltage", "V", "pv"),
    Entity("pv1_current", "PV string 1 current", "A", "pv"),
    Entity("total_pv_generation", "Total PV generation", "kWh", "pv"),

    # Battery
    Entity("day_battery_discharge", "Daily battery discharge", "kWh", "battery"),
    Entity("day_battery_charge", "Daily battery charge", "kWh", "battery"),
    Entity("battery_power", "Battery power (+ charging, - discharging)", "W", "battery"),
    Entity("battery_current", "Battery current", "A", "battery"),
    Entity("battery_temp", "Battery temperature", "°C", "battery"),
    Entity("battery_voltage", "Battery voltage", "V", "battery"),
    Entity("battery_soc", "Battery state of charge", "%", "battery"),
    Entity("battery_soh", "Battery state of health", "%", "battery"),

    # Inverter - basic (L1 always required)
    Entity("inverter_status", "Inverter status", "-", "inverter"),
    Entity("inverter_voltage_l1", "L1 voltage", "V", "inverter"),
    Entity("inverter_current_l1", "L1 current", "A", "inverter"),
    Entity("inverter_power", "Inverter power", "W", "inverter"),

    # Grid - basic
    Entity("grid_power", "Grid power (+ import, - export)", "W", "grid"),
    Entity("day_grid_import", "Daily grid import", "kWh", "grid"),
    Entity("day_grid_export", "Daily grid export", "kWh", "grid"),
    Entity("grid_connected_status", "Grid connection status", "bool", "grid"),

    # Load - basic
    Entity("day_load_energy", "Daily load energy", "kWh", "load"),
    Entity("load_power_l1", "Load L1 power", "W", "load"),
    Entity("load_frequency", "Grid frequency", "Hz", "load"),

    # Temperatures
    Entity("radiator_temp", "Radiator temperature", "°C", "temp"),
    Entity("dc_transformer_temp", "DC transformer temperature", "°C", "temp"),
]

# Optional entities (depending on installation: e.g., 2nd/3rd PV string, 3-phase setup)
OPTIONAL_ENTITIES = [
    # PV - additional strings (up to 3, optional for >1)
    Entity("pv2_power", "PV string 2 power", "W", "pv"),
    Entity("pv2_voltage", "PV string 2 voltage", "V", "pv"),
    Entity("pv2_current", "PV string 2 current", "A", "pv"),
    Entity("pv3_power", "PV string 3 power", "W", "pv"),
    Entity("pv3_voltage", "PV string 3 voltage", "V", "pv"),
    Entity("pv3_current", "PV string 3 current", "A", "pv"),

    # Inverter - additional phases (L2/L3 optional for <3 phases)
    Entity("inverter_voltage_l2", "L2 voltage", "V", "inverter"),
    Entity("inverter_voltage_l3", "L3 voltage", "V", "inverter"),
    Entity("inverter_current_l2", "L2 current", "A", "inverter"),
    Entity("inverter_current_l3", "L3 current", "A", "inverter"),

    # Grid - additional CT phases (optional for <3 phases)
    Entity("grid_ct_power_l1", "CT L1 power", "W", "grid"),
    Entity("grid_ct_power_l2", "CT L2 power", "W", "grid"),
    Entity("grid_ct_power_l3", "CT L3 power", "W", "grid"),

    # Load - additional phases (optional for <3 phases)
    Entity("load_power_l2", "Load L2 power", "W", "load"),
    Entity("load_power_l3", "Load L3 power", "W", "load"),
]

# All entities (required + optional) for completeness
ALL_ENTITIES = REQUIRED_ENTITIES + OPTIONAL_ENTITIES

# Entity keys for easy access
ENTITY_KEYS = [entity.key for entity in ALL_ENTITIES]

# Grouped entities by category
ENTITY_CATEGORIES = {
    "pv": "Photovoltaic Panels (PV)",
    "battery": "Battery",
    "inverter": "Inverter",
    "grid": "Grid",
    "load": "Load",
    "temp": "Temperatures",
}


def build_solarman_entity_mapping(prefix: str) -> dict[str, str]:
    """Build entity mapping for Solarman integration based on prefix."""
    if not prefix or not prefix.replace("_", "").isalnum():
        raise ValueError("Invalid prefix for Solarman mapping")
    return {
        # PV
        "day_pv_energy": f"sensor.{prefix}_today_production",
        "pv1_power": f"sensor.{prefix}_pv1_power",
        "pv2_power": f"sensor.{prefix}_pv2_power",
        "pv3_power": f"sensor.{prefix}_pv3_power",  # Added for third string
        "pv1_voltage": f"sensor.{prefix}_pv1_voltage",
        "pv2_voltage": f"sensor.{prefix}_pv2_voltage",
        "pv3_voltage": f"sensor.{prefix}_pv3_voltage",  # Added
        "pv1_current": f"sensor.{prefix}_pv1_current",
        "pv2_current": f"sensor.{prefix}_pv2_current",
        "pv3_current": f"sensor.{prefix}_pv3_current",  # Added
        "total_pv_generation": f"sensor.{prefix}_total_production",
        
        # Battery
        "day_battery_discharge": f"sensor.{prefix}_today_battery_discharge",
        "day_battery_charge": f"sensor.{prefix}_today_battery_charge",
        "battery_power": f"sensor.{prefix}_battery_power",
        "battery_current": f"sensor.{prefix}_battery_current",
        "battery_temp": f"sensor.{prefix}_battery_temperature",
        "battery_voltage": f"sensor.{prefix}_battery_voltage",
        "battery_soc": f"sensor.{prefix}_battery",
        "battery_soh": f"sensor.{prefix}_battery_soh",
        
        # Inverter
        "inverter_status": f"sensor.{prefix}_device_relay",
        "inverter_voltage_l1": f"sensor.{prefix}_grid_l1_voltage",
        "inverter_voltage_l2": f"sensor.{prefix}_grid_l2_voltage",
        "inverter_voltage_l3": f"sensor.{prefix}_grid_l3_voltage",
        "inverter_current_l1": f"sensor.{prefix}_internal_ct1_current",
        "inverter_current_l2": f"sensor.{prefix}_internal_ct2_current",
        "inverter_current_l3": f"sensor.{prefix}_internal_ct3_current",
        "inverter_power": f"sensor.{prefix}_internal_power",
        
        # Grid
        "grid_power": f"sensor.{prefix}_grid_power",
        "grid_ct_power_l1": f"sensor.{prefix}_grid_l1_power",
        "grid_ct_power_l2": f"sensor.{prefix}_grid_l2_power",
        "grid_ct_power_l3": f"sensor.{prefix}_grid_l3_power",
        "day_grid_import": f"sensor.{prefix}_today_energy_import",
        "day_grid_export": f"sensor.{prefix}_today_energy_export",
        "grid_connected_status": f"binary_sensor.{prefix}_grid",
        
        # Load
        "day_load_energy": f"sensor.{prefix}_today_load_consumption",
        "load_power_l1": f"sensor.{prefix}_load_l1_power",
        "load_power_l2": f"sensor.{prefix}_load_l2_power",
        "load_power_l3": f"sensor.{prefix}_load_l3_power",
        "load_frequency": f"sensor.{prefix}_grid_frequency",
        
        # Temperatures
        "radiator_temp": f"sensor.{prefix}_temperature",
        "dc_transformer_temp": f"sensor.{prefix}_dc_temperature",
    }

# Dobre praktyki dla integracji Home Assistant (wg dokumentacji developers.home-assistant.io):
# 1. Stałe: Używaj UPPER_CASE dla nazw stałych, dokumentuj jednostki i klasy urządzeń.
# 2. Sensory: Używaj odpowiednich device_class (np. ENERGY dla energii, POWER dla mocy, VOLTAGE dla napięcia, CURRENT dla prądu, TEMPERATURE dla temperatury).
#    - Dla energii: SensorDeviceClass.ENERGY, jednostki: kWh, Wh itp.
#    - Dla mocy: SensorDeviceClass.POWER, jednostki: W, kW.
#    - Dla napięcia/prądu: SensorDeviceClass.VOLTAGE/CURRENT, jednostki: V/A.
#    - Dla temperatury: SensorDeviceClass.TEMPERATURE, jednostki: °C.
# 3. State_class: MEASUREMENT dla bieżących pomiarów, TOTAL dla sum kumulatywnych, TOTAL_INCREASING dla rosnących sum (np. energia dzienna).
# 4. Opcjonalne encje: Sprawdzaj dostępność sensorów w runtime, nie zakładaj, że wszystkie istnieją (np. brak L2/L3 w instalacjach jednofazowych).
# 5. Walidacja: Dodaj sprawdzenie w config_flow, czy wymagane sensory są dostępne.
# 6. Style kodu: Używaj f-strings, type hints, docstrings w stylu Google. Stałe w alfabetycznym porządku.
# 7. Unikaj hardkodowanych wartości: Używaj config_entry zamiast globalnych stałych dla ustawień użytkownika.
# 8. Testowanie: Dodaj testy jednostkowe dla mapowania i walidacji encji.
# 9. Dokumentacja: Opisuj jednostki i znaczenie każdej encji w komentarzach.
# 10. Aktualizacje: Monitoruj zmiany w HA API (np. nowe device_class) i aktualizuj integrację.
