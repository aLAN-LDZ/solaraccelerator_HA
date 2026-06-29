"""Stałe globalne integracji Solar Accelerator.

Trzy główne grupy:
- klucze konfiguracji (``CONF_*``) — używane w config flow i ``entry.data``,
- endpointy serwisu (``API_*``)   — relatywne ścieżki na serwerze,
- definicja wymaganych encji       — kanoniczna lista pól które wysyłamy do API.

Domyślne mapowania ``klucz_kanoniczny → entity_id`` dla poszczególnych sposobów
połączenia (Solarman, SolarAssistant, OCPP) żyją w pakiecie ``profiles/``.
"""

DOMAIN = "solaraccelerator"

# === Klucze konfiguracji (config flow + entry.data) ===
CONF_API_KEY = "api_key"
CONF_SERVER_URL = "server_url"
CONF_ENTITY_MAPPING = "entity_mapping"
CONF_CONFIG_MODE = "config_mode"
CONF_SOLARMAN_PREFIX = "solarman_prefix"
CONF_EV_ENABLED = "ev_enabled"
CONF_EV_PREFIX = "ev_prefix"
CONF_EV_CONFIG_MODE = "ev_config_mode"
CONF_INVERTER_MODEL = "inverter_model"
CONF_EV_MODEL = "ev_model"

# Custom sterowalne odbiorniki dodawane w OptionsFlow (przycisk "Konfiguruj").
# Lista słowników: {key, label, device_type, switch_entity, power_sensor,
# energy_sensor, status_entity, nominal_power_w}. Trzymane w entry.options.
CONF_CONTROLLABLE_DEVICES = "controllable_devices"

# Szkic profilu tworzony w OptionsFlow (kreator "Zgłoś / eksportuj profil").
# Słownik: {manufacturer, model, source, prefix, capabilities{}, control_mapping{}}.
# Trzymany w entry.options; czytany przez diagnostics.py do wygenerowania eksportu.
CONF_PROFILE_DRAFT = "profile_draft"

# Typy sterowalnych odbiorników (do selecta w OptionsFlow). Wartość ``value``
# jest wysyłana do serwisu jako typ urządzenia.
CONTROLLABLE_DEVICE_TYPES = [
    {"value": "ev", "label": "Ładowarka EV"},
    {"value": "cwu", "label": "CWU / bojler"},
    {"value": "hvac", "label": "Klimatyzacja / pompa ciepła"},
    {"value": "other", "label": "Inne"},
]

# Tryby konfiguracji wybierane w config flow:
# - SOLARMAN:       użytkownik podaje prefix integracji Solarman/HACS, budujemy mapowanie automatycznie
# - SOLARASSISTANT: użytkownik podaje prefix urządzenia SolarAssistant (MQTT), mapowanie automatyczne
# - MANUAL:         użytkownik mapuje każdą encję ręcznie
CONFIG_MODE_SOLARMAN = "solarman"
CONFIG_MODE_SOLARASSISTANT = "solarassistant"
CONFIG_MODE_MANUAL = "manual"

# Schemat nazw encji używany, gdy tryb nie ma profilu (tryb ręczny / nieznany).
DEFAULT_ENTITY_SCHEME = CONFIG_MODE_SOLARMAN

# Domyślny URL serwisu (można nadpisać w config flow np. dla self-hosted)
DEFAULT_SERVER_URL = "https://solaraccelerator.cloud"

# Wspierane modele urządzeń wynikają z profili w pakiecie ``profiles/`` — kreator
# buduje listę wyboru bezpośrednio z rejestru profili (model jest częścią profilu).

# Klucze atrybutów sensorów — używane do referencji w innych miejscach
ATTR_LAST_SENT = "last_sent"
ATTR_LAST_RECEIVED = "last_received"
ATTR_CONNECTION_STATUS = "connection_status"
ATTR_ENTITIES_COUNT = "entities_count"
ATTR_NEXT_SCHEDULED = "next_scheduled"

# === Endpointy serwisu (ścieżki względne, base URL trzyma config flow) ===
API_TEST_CONNECTION_ENDPOINT = "/api/homeassistant/test-connection"
API_SEND_DATA_ENDPOINT = "/api/homeassistant/send-data"
API_LIVE_ENDPOINT = "/api/homeassistant/live"
API_DATA_READY_ENDPOINT = "/api/homeassistant/data-ready"
API_PRICES_ENDPOINT = "/api/homeassistant/prices"
API_PROFIT_ENDPOINT = "/api/homeassistant/profit"
API_COMMAND_ACK_ENDPOINT = "/api/homeassistant/commands/{id}/ack"

# === Ustawienia kanału live ===
# Wartość początkowa interwału — używana zanim serwer poda właściwą w odpowiedzi
DEFAULT_LIVE_INTERVAL = 15
# Po HTTP 503 (admin wyłączył kanał) — sprawdzamy ponownie co minutę
LIVE_DISABLED_RETRY = 60
# Po HTTP 401 (zły klucz API) — długa pauza, żeby nie zalewać serwera
LIVE_AUTH_RETRY = 300

# === Write manager — kolejka komend wysyłanych do falownika ===
# Falownik (Modbus przez Solarman) nie nadąża gdy uderza w niego kilka write naraz —
# część komend jest odrzucana. Dlatego komendy idą przez kolejkę z dwoma opóźnieniami:
#   1. ``command_delay`` — pauza między kolejnymi write w obrębie jednej batch'y,
#   2. ``verify_settling`` — pauza po ostatnim write, zanim odczytamy wartości do weryfikacji.
# Obie wartości są wystawione jako encje number, żeby tunować je w UI bez restartu integracji.
DEFAULT_COMMAND_DELAY = 1.5      # sekund między write
MIN_COMMAND_DELAY = 0.1
MAX_COMMAND_DELAY = 10.0

DEFAULT_VERIFY_SETTLING = 5.0    # sekund od ostatniego write do pierwszego verify
MIN_VERIFY_SETTLING = 1.0
MAX_VERIFY_SETTLING = 120.0

# Verify retry — gdy verify pokaże że falownik nie przyjął write (np. Modbus
# odrzucił pakiet), ponawiamy execute+verify do MAX prób. Tylko dla komend
# które wykonały się bez wyjątku — encja unavailable nie jest retry'owana.
DEFAULT_VERIFY_RETRIES = 3       # liczba dodatkowych prób po pierwszym fail
MIN_VERIFY_RETRIES = 0           # 0 = brak retry, klasyczne zachowanie
MAX_VERIFY_RETRIES = 10

# === Guard "Pilnuj ustawień" — pilnowanie stanu sterowanych encji ===
# Po każdej komendzie serwisu guard zapamiętuje docelowy stan encji i przez całą
# godzinę pilnuje, żeby ten stan się utrzymał. Falownik Deye/Solarman po Modbusie
# potrafi SAM zresetować rejestr do wcześniejszej wartości po kilku–kilkunastu
# minutach — verify dawno przeszedł, ACK wysłany, a plan przestaje być realizowany.
# Guard wykrywa odchylenie (przez zdarzenie zmiany stanu LUB okresowy sweep) i
# wysyła komendę przywracającą wartość z planu. Sterowany przełącznikiem switch.py.
DATA_GUARD_ENABLED = "guard_enabled"   # klucz w coordinator_data
DEFAULT_GUARD_ENABLED = True           # domyślnie ON — plan egzekwowany od razu po instalacji

# Co ile sekund guard re-sprawdza WSZYSTKIE pilnowane encje (sweep). Łapie
# przypadek "falownik utknął na złej wartości bez emitowania zdarzenia zmiany"
# oraz cichą porażkę poprzedniej korekty — bo pojedynczy write nie daje pewności.
GUARD_SWEEP_INTERVAL = 60

# Lista wszystkich pól które integracja może wysyłać do serwisu.
# Format: (key, description, unit, category)
# - ``key``         — nazwa pola w payloadzie API,
# - ``description`` — czytelny opis (używany w UI config flow),
# - ``unit``        — jednostka (informacyjnie),
# - ``category``    — przypisuje encję do jednej grupy w config flow (pv/battery/...).
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

    # Ładowarka EV (OCPP) — klucze BEZ prefiksu ev_, kategoria daje kontekst
    ("status", "Status ładowarki", "-", "ev_charger"),
    ("status_connector", "Status połączenia", "-", "ev_charger"),
    ("vendor", "Producent ładowarki", "-", "ev_charger"),
    ("power_active_import", "Moc ładowania", "kW", "ev_charger"),
    ("energy_session", "Energia sesji", "kWh", "ev_charger"),
    ("energy_active_import_register", "Licznik energii", "kWh", "ev_charger"),
    ("current_import", "Prąd ładowania", "A", "ev_charger"),
    ("voltage", "Napięcie", "V", "ev_charger"),
    ("time_session", "Czas sesji", "min", "ev_charger"),
    ("error_code", "Kod błędu", "-", "ev_charger"),
    ("transaction_id", "ID transakcji", "-", "ev_charger"),
]

# Encje falownika — wszystko z REQUIRED_ENTITIES poza kategorią ev_charger
INVERTER_ENTITIES = [e for e in REQUIRED_ENTITIES if e[3] != "ev_charger"]
INVERTER_KEYS = [e[0] for e in INVERTER_ENTITIES]

# Encje ładowarki EV (OCPP) — wydzielone, bo wysyłane tylko gdy użytkownik włączył EV
EV_ENTITIES = [e for e in REQUIRED_ENTITIES if e[3] == "ev_charger"]
EV_ENTITY_KEYS = [e[0] for e in EV_ENTITIES]

# Wszystkie klucze encji w jednej liście — pomocnicze
ENTITY_KEYS = [entity[0] for entity in REQUIRED_ENTITIES]

# Mapowanie kategorii na czytelne nazwy używane w UI config flow
ENTITY_CATEGORIES = {
    "pv": "Panele fotowoltaiczne (PV)",
    "battery": "Bateria",
    "inverter": "Inwerter",
    "grid": "Sieć",
    "load": "Obciążenie",
    "temp": "Temperatury",
    "ev_charger": "Ładowarka EV",
}
