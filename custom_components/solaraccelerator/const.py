"""Constants for the Solar Accelerator integration."""

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

# All 36 required entities for SolarAccelerator API
# Format: (key, description, unit, category)
REQUIRED_ENTITIES = [
    # PV (Panele fotowoltaiczne)
    ("day_pv_energy", "Dzienna produkcja PV", "kWh", "pv"),
    ("pv1_power", "Moc PV string 1", "W", "pv"),
    ("pv2_power", "Moc PV string 2", "W", "pv"),
    ("pv1_voltage", "Napięcie PV string 1", "V", "pv"),
    ("pv2_voltage", "Napięcie PV string 2", "V", "pv"),
    ("pv1_current", "Prąd PV string 1", "A", "pv"),
    ("pv2_current", "Prąd PV string 2", "A", "pv"),
    ("total_pv_generation", "Całkowita generacja PV", "kWh", "pv"),

    # Bateria
    ("day_battery_discharge", "Dzienne rozładowanie baterii", "kWh", "battery"),
    ("day_battery_charge", "Dzienne ładowanie baterii", "kWh", "battery"),
    ("battery_power", "Moc baterii (+ ładowanie, - rozładowanie)", "W", "battery"),
    ("battery_current", "Prąd baterii", "A", "battery"),
    ("battery_temp", "Temperatura baterii", "°C", "battery"),
    ("battery_voltage", "Napięcie baterii", "V", "battery"),
    ("battery_soc", "Stan naładowania baterii", "%", "battery"),
    ("battery_soh", "Stan zdrowia baterii", "%", "battery"),

    # Inwerter
    ("inverter_status", "Status inwertera", "-", "inverter"),
    ("inverter_voltage_l1", "Napięcie L1", "V", "inverter"),
    ("inverter_voltage_l2", "Napięcie L2", "V", "inverter"),
    ("inverter_voltage_l3", "Napięcie L3", "V", "inverter"),
    ("inverter_current_l1", "Prąd L1", "A", "inverter"),
    ("inverter_current_l2", "Prąd L2", "A", "inverter"),
    ("inverter_current_l3", "Prąd L3", "A", "inverter"),
    ("inverter_power", "Moc inwertera", "W", "inverter"),

    # Sieć
    ("grid_power", "Moc sieci (+ pobór, - oddawanie)", "W", "grid"),
    ("grid_ct_power_l1", "Moc CT L1", "W", "grid"),
    ("grid_ct_power_l2", "Moc CT L2", "W", "grid"),
    ("grid_ct_power_l3", "Moc CT L3", "W", "grid"),
    ("day_grid_import", "Dzienny pobór z sieci", "kWh", "grid"),
    ("day_grid_export", "Dzienne oddanie do sieci", "kWh", "grid"),
    ("grid_connected_status", "Status połączenia z siecią", "bool", "grid"),

    # Obciążenie
    ("day_load_energy", "Dzienne zużycie", "kWh", "load"),
    ("load_power_l1", "Moc obciążenia L1", "W", "load"),
    ("load_power_l2", "Moc obciążenia L2", "W", "load"),
    ("load_power_l3", "Moc obciążenia L3", "W", "load"),
    ("load_frequency", "Częstotliwość sieci", "Hz", "load"),

    # Temperatury
    ("radiator_temp", "Temperatura radiatora", "°C", "temp"),
    ("dc_transformer_temp", "Temperatura transformatora DC", "°C", "temp"),
]

# Entity keys for easy access
ENTITY_KEYS = [entity[0] for entity in REQUIRED_ENTITIES]

# Grouped entities by category
ENTITY_CATEGORIES = {
    "pv": "Panele fotowoltaiczne (PV)",
    "battery": "Bateria",
    "inverter": "Inwerter",
    "grid": "Sieć",
    "load": "Obciążenie",
    "temp": "Temperatury",
}


def build_solarman_entity_mapping(prefix: str) -> dict[str, str]:
    """Build entity mapping for Solarman integration based on prefix."""
    return {
        "day_pv_energy": f"sensor.{prefix}_today_production",
        "pv1_power": f"sensor.{prefix}_pv1_power",
        "pv2_power": f"sensor.{prefix}_pv2_power",
        "pv1_voltage": f"sensor.{prefix}_pv1_voltage",
        "pv2_voltage": f"sensor.{prefix}_pv2_voltage",
        "pv1_current": f"sensor.{prefix}_pv1_current",
        "pv2_current": f"sensor.{prefix}_pv2_current",
        "total_pv_generation": f"sensor.{prefix}_total_production",
        "day_battery_discharge": f"sensor.{prefix}_today_battery_discharge",
        "day_battery_charge": f"sensor.{prefix}_today_battery_charge",
        "battery_power": f"sensor.{prefix}_battery_power",
        "battery_current": f"sensor.{prefix}_battery_current",
        "battery_temp": f"sensor.{prefix}_battery_temperature",
        "battery_voltage": f"sensor.{prefix}_battery_voltage",
        "battery_soc": f"sensor.{prefix}_battery",
        "battery_soh": f"sensor.{prefix}_battery_soh",
        "inverter_status": f"sensor.{prefix}_device_relay",
        "inverter_voltage_l1": f"sensor.{prefix}_grid_l1_voltage",
        "inverter_voltage_l2": f"sensor.{prefix}_grid_l2_voltage",
        "inverter_voltage_l3": f"sensor.{prefix}_grid_l3_voltage",
        "inverter_current_l1": f"sensor.{prefix}_internal_ct1_current",
        "inverter_current_l2": f"sensor.{prefix}_internal_ct2_current",
        "inverter_current_l3": f"sensor.{prefix}_internal_ct3_current",
        "inverter_power": f"sensor.{prefix}_internal_power",
        "grid_power": f"sensor.{prefix}_grid_power",
        "grid_ct_power_l1": f"sensor.{prefix}_grid_l1_power",
        "grid_ct_power_l2": f"sensor.{prefix}_grid_l2_power",
        "grid_ct_power_l3": f"sensor.{prefix}_grid_l3_power",
        "day_grid_import": f"sensor.{prefix}_today_energy_import",
        "day_grid_export": f"sensor.{prefix}_today_energy_export",
        "grid_connected_status": f"binary_sensor.{prefix}_grid",
        "day_load_energy": f"sensor.{prefix}_today_load_consumption",
        "load_power_l1": f"sensor.{prefix}_load_l1_power",
        "load_power_l2": f"sensor.{prefix}_load_l2_power",
        "load_power_l3": f"sensor.{prefix}_load_l3_power",
        "load_frequency": f"sensor.{prefix}_grid_frequency",
        "radiator_temp": f"sensor.{prefix}_temperature",
        "dc_transformer_temp": f"sensor.{prefix}_dc_temperature",
    }
