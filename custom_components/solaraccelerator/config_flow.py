"""Config flow integracji Solar Accelerator.

Kroki dodawania integracji:
1. ``user``                — klucz API + URL serwera (walidacja przez GET test-connection),
2. ``choose_mode``         — wybór modelu falownika i trybu (profil przez prefix / ręcznie),
3a. ``prefix``             — gdy wybrano profil: prefix encji, z którego budujemy mapowanie,
3b. ``entities_pv/...``    — gdy tryb manualny: mapowanie encji w 6 ekranach (PV, bateria,
   inwerter, sieć, obciążenie, temperatury),
4. ``ev_charger``          — pytanie czy użytkownik ma ładowarkę EV,
5a-5c. analogicznie do kroków 2-3 dla ładowarki (jeśli włączona).

Stan między krokami trzymamy w polach klasy ``SolarAcceleratorConfigFlow``.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util import slugify

from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_SERVER_URL,
    CONF_ENTITY_MAPPING,
    CONF_CONFIG_MODE,
    CONF_SOLARMAN_PREFIX,
    CONF_EV_ENABLED,
    CONF_EV_PREFIX,
    CONF_EV_CONFIG_MODE,
    CONF_INVERTER_MANUFACTURER,
    CONF_INVERTER_MODEL,
    CONF_EV_MODEL,
    CONF_CONTROLLABLE_DEVICES,
    CONF_PROFILE_DRAFT,
    CONTROLLABLE_DEVICE_TYPES,
    CONFIG_MODE_SOLARMAN,
    CONFIG_MODE_MANUAL,
    DEFAULT_SERVER_URL,
    API_TEST_CONNECTION_ENDPOINT,
    REQUIRED_ENTITIES,
    ENTITY_CATEGORIES,
    INVERTER_KEYS,
    EV_ENTITY_KEYS,
)
from . import contract
from .profile_export import build_profile_draft, detect_prefix
from .profiles import (
    ROLE_EV_CHARGER,
    get_profile,
    list_profiles,
    list_sources_for_inverter,
    list_supported_inverters,
)

# Nazwy pól formularza kreatora (wybór wspieranego falownika i źródła).
CONF_INVERTER = "inverter"
CONF_SOURCE = "source"

# Domeny encji dopuszczone przy mapowaniu STEROWANIA — tylko encje ustawialne (sterowanie
# bywa wystawione jako number/select/switch/time itd. zależnie od integracji). Kodek
# zostanie dobrany później ze snapshotu, więc nie zawężamy do typu kanonicznego knoba.
CONTROL_ENTITY_DOMAINS = [
    "number",
    "input_number",
    "select",
    "input_select",
    "switch",
    "input_boolean",
    "time",
    "input_datetime",
]

_LOGGER = logging.getLogger(__name__)


async def async_validate_api_key(
    hass: HomeAssistant,
    api_key: str,
    server_url: str,
) -> dict[str, Any]:
    """Sprawdź klucz API wysyłając GET na endpoint test-connection.

    Zwraca słownik z polem ``success`` (bool) oraz, w przypadku błędu, kodem
    ``error`` używanym przez UI do pokazania właściwego komunikatu:
    - ``invalid_api_key``    — HTTP 401 (zły klucz),
    - ``integration_disabled`` — HTTP 403 (integracja wyłączona po stronie serwera),
    - ``cannot_connect``     — błąd sieci lub timeout lub inny kod HTTP,
    - ``unknown``            — nieoczekiwany wyjątek.
    """
    try:
        session = async_get_clientsession(hass)
        server_url = server_url.rstrip("/")
        endpoint = f"{server_url}{API_TEST_CONNECTION_ENDPOINT}"

        _LOGGER.debug("Test połączenia: %s", endpoint)

        async with session.get(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
            },
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            text = await resp.text()
            _LOGGER.debug("Odpowiedź API: status=%s, body=%s", resp.status, text[:200])

            if resp.status == 200:
                return {"success": True}
            elif resp.status == 401:
                return {"success": False, "error": "invalid_api_key"}
            elif resp.status == 403:
                return {"success": False, "error": "integration_disabled"}
            else:
                _LOGGER.error("Walidacja API nieudana: %s - %s", resp.status, text)
                return {"success": False, "error": "cannot_connect"}
    except aiohttp.ClientConnectorError as e:
        _LOGGER.error("Błąd połączenia z %s: %s", server_url, e)
        return {"success": False, "error": "cannot_connect"}
    except aiohttp.ClientError as e:
        _LOGGER.error("Błąd klienta HTTP: %s", e)
        return {"success": False, "error": "cannot_connect"}
    except asyncio.TimeoutError:
        _LOGGER.error("Timeout połączenia z %s", server_url)
        return {"success": False, "error": "cannot_connect"}
    except Exception as e:
        _LOGGER.exception("Walidacja API nieudana: %s", e)
        return {"success": False, "error": "unknown"}


def get_entities_for_category(category: str) -> list[tuple[str, str, str, str]]:
    """Zwróć wszystkie wymagane encje należące do danej kategorii (pv/battery/...)."""
    return [e for e in REQUIRED_ENTITIES if e[3] == category]


def _model_label(profile) -> str:
    """Czytelny model urządzenia z profilu (lub 'manual' dla trybu ręcznego)."""
    return f"{profile.manufacturer} {profile.model}" if profile else CONFIG_MODE_MANUAL


class SolarAcceleratorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Obsługa config flow Solar Accelerator — krokowy kreator dodawania integracji."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "SolarAcceleratorOptionsFlow":
        """Przycisk 'Konfiguruj' na karcie integracji → zarządzanie udostępnianymi encjami."""
        return SolarAcceleratorOptionsFlow(config_entry)

    def __init__(self) -> None:
        """Zainicjalizuj puste pola — zostaną wypełnione w kolejnych krokach kreatora."""
        self.api_key: str = ""
        self.server_url: str = DEFAULT_SERVER_URL
        self.config_mode: str = ""
        self.solarman_prefix: str = ""
        self.inverter_manufacturer: str = ""
        self.inverter_model: str = ""
        self.ev_enabled: bool = False
        self.ev_config_mode: str = ""
        self.ev_prefix: str = ""
        self.ev_model: str = ""
        self.entity_mapping: dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Pierwszy krok — pobranie i walidacja klucza API + URL serwera."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY, "").strip()
            server_url = user_input.get(CONF_SERVER_URL, DEFAULT_SERVER_URL).strip()

            # Walidacja formatu klucza — musi zaczynać się od "sa_haapi_" i mieć min. 40 znaków
            if not api_key.startswith("sa_haapi_"):
                errors[CONF_API_KEY] = "invalid_api_key_format"
            elif len(api_key) < 40:
                errors[CONF_API_KEY] = "invalid_api_key_format"

            # Walidacja formatu URL — wymagamy schematu http/https
            if not server_url.startswith(("http://", "https://")):
                errors[CONF_SERVER_URL] = "invalid_url"

            if not errors:
                # Sprawdzenie klucza po stronie serwera (GET na test-connection)
                result = await async_validate_api_key(self.hass, api_key, server_url)

                if result["success"]:
                    self.api_key = api_key
                    self.server_url = server_url.rstrip("/")
                    return await self.async_step_choose_inverter()
                else:
                    errors["base"] = result.get("error", "cannot_connect")

        schema = vol.Schema({
            vol.Required(CONF_API_KEY): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_SERVER_URL, default=DEFAULT_SERVER_URL): TextSelector(
                TextSelectorConfig(type=TextSelectorType.URL)
            ),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_choose_inverter(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Krok 1: wybór wspieranego falownika.

        Wsparcie jest na poziomie falownika (podejście do sterowania w kodzie), nie
        samego mapowania encji. Inny falownik = inne podejście — dlatego najpierw
        użytkownik wybiera swój wspierany model, a dopiero potem źródło.
        """
        if user_input is not None:
            manufacturer, model = user_input[CONF_INVERTER].split("|", 1)
            self.inverter_manufacturer = manufacturer
            self.inverter_model = model
            return await self.async_step_choose_source()

        inverter_options = [
            {"value": f"{manufacturer}|{model}", "label": f"{manufacturer} {model}"}
            for manufacturer, model in list_supported_inverters()
        ]

        schema = vol.Schema({
            vol.Required(CONF_INVERTER, default=inverter_options[0]["value"]): SelectSelector(
                SelectSelectorConfig(
                    options=inverter_options,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
        })

        return self.async_show_form(
            step_id="choose_inverter",
            data_schema=schema,
        )

    async def async_step_choose_source(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Krok 2: jak wybrany falownik jest wystawiony w HA (źródło) albo ręczne mapowanie.

        Oficjalne źródła to gotowe profile dla tego falownika. „Ręczne mapowanie"
        służy do skonfigurowania tego samego (wspieranego) falownika wystawionego
        przez źródło, którego nie mamy jeszcze oficjalnie — i do zgłoszenia go.
        """
        sources = list_sources_for_inverter(self.inverter_manufacturer, self.inverter_model)

        if user_input is not None:
            choice = user_input[CONF_SOURCE]
            if choice == CONFIG_MODE_MANUAL:
                self.config_mode = CONFIG_MODE_MANUAL
                return await self.async_step_entities_pv()
            # Wartość to id profilu (źródło×falownik).
            self.config_mode = choice
            return await self.async_step_prefix()

        source_options = [
            {"value": profile_id, "label": label} for _slug, label, profile_id in sources
        ]
        source_options.append(
            {"value": CONFIG_MODE_MANUAL, "label": "Ręczne mapowanie (źródło spoza listy)"}
        )

        schema = vol.Schema({
            vol.Required(CONF_SOURCE, default=source_options[0]["value"]): SelectSelector(
                SelectSelectorConfig(
                    options=source_options,
                    mode=SelectSelectorMode.LIST,
                )
            ),
        })

        return self.async_show_form(
            step_id="choose_source",
            data_schema=schema,
            description_placeholders={
                "inverter": f"{self.inverter_manufacturer} {self.inverter_model}",
            },
        )

    async def async_step_prefix(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Pobierz prefix encji i zbuduj domyślne mapowanie wg wybranego profilu.

        Prefix zapisujemy w ``CONF_SOLARMAN_PREFIX`` — to z tego pola budowany jest
        ``inverterPrefix`` w paczce danych (wspólne dla wszystkich profili falownika).
        Użytkownik może później ręcznie skorygować pojedyncze encje.
        """
        profile = get_profile(self.config_mode)
        errors: dict[str, str] = {}

        if user_input is not None:
            prefix = user_input.get(CONF_SOLARMAN_PREFIX, "").strip().lower()

            if not prefix:
                errors[CONF_SOLARMAN_PREFIX] = "prefix_required"
            elif " " in prefix or not prefix.replace("_", "").isalnum():
                errors[CONF_SOLARMAN_PREFIX] = "invalid_prefix"
            elif profile is None:
                errors["base"] = "unknown"
            else:
                self.solarman_prefix = prefix
                self.entity_mapping = profile.build_mapping(prefix)
                return await self.async_step_ev_charger()

        schema = vol.Schema({
            vol.Required(CONF_SOLARMAN_PREFIX): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            ),
        })

        return self.async_show_form(
            step_id="prefix",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "profile_label": profile.label if profile else "",
                "prefix_example": profile.prefix_example if profile else "",
            },
        )

    async def _async_step_entities(
        self, category: str, next_step: str | None, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Wspólna obsługa kroków mapowania encji.

        Dla każdej kategorii (pv, battery, inverter, grid, load, temp, ev_charger) pokazuje
        formularz z polami EntitySelector — po jednym dla każdej wymaganej encji w kategorii.
        Po zatwierdzeniu zapisuje mapowanie w ``self.entity_mapping`` i przechodzi do
        ``next_step`` (lub kończy kreator gdy ``next_step is None``).
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            category_entities = get_entities_for_category(category)
            all_filled = True

            for entity_key, _, _, _ in category_entities:
                mapped_entity = user_input.get(entity_key, "")
                if mapped_entity:
                    self.entity_mapping[entity_key] = mapped_entity
                else:
                    all_filled = False
                    errors[entity_key] = "entity_required"

            if all_filled:
                if next_step:
                    return await getattr(self, f"async_step_{next_step}")()
                else:
                    return self._create_entry()

        category_entities = get_entities_for_category(category)
        schema_dict = {}

        for entity_key, description, unit, _ in category_entities:
            default_value = self.entity_mapping.get(entity_key, vol.UNDEFINED)
            schema_dict[vol.Required(entity_key, default=default_value)] = EntitySelector(
                EntitySelectorConfig(domain=["sensor", "binary_sensor"])
            )

        return self.async_show_form(
            step_id=f"entities_{category}",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={
                "category_name": ENTITY_CATEGORIES.get(category, category),
            },
        )

    async def async_step_entities_pv(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Mapowanie encji PV (panele fotowoltaiczne)."""
        return await self._async_step_entities("pv", "entities_battery", user_input)

    async def async_step_entities_battery(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Mapowanie encji baterii."""
        return await self._async_step_entities("battery", "entities_inverter", user_input)

    async def async_step_entities_inverter(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Mapowanie encji inwertera."""
        return await self._async_step_entities("inverter", "entities_grid", user_input)

    async def async_step_entities_grid(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Mapowanie encji sieci elektroenergetycznej."""
        return await self._async_step_entities("grid", "entities_load", user_input)

    async def async_step_entities_load(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Mapowanie encji obciążenia (zużycia domowego)."""
        return await self._async_step_entities("load", "entities_temp", user_input)

    async def async_step_entities_temp(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Mapowanie encji temperatur (radiator, transformator DC)."""
        return await self._async_step_entities("temp", "ev_charger", user_input)

    async def async_step_ev_charger(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Pytanie czy użytkownik ma ładowarkę EV obsługiwaną przez integrację OCPP."""
        if user_input is not None:
            self.ev_enabled = bool(user_input.get(CONF_EV_ENABLED, False))

            if self.ev_enabled:
                return await self.async_step_ev_choose_mode()
            else:
                return self._create_entry()

        schema = vol.Schema({
            vol.Required(CONF_EV_ENABLED, default=False): bool,
        })

        return self.async_show_form(
            step_id="ev_charger",
            data_schema=schema,
        )

    async def async_step_ev_choose_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Wybór trybu konfiguracji ładowarki EV (prefix OCPP vs ręcznie).

        Model ładowarki pochodzi z profilu EV (nie ma osobnego pola modelu).
        """
        if user_input is not None:
            self.ev_model = _model_label(list_profiles(ROLE_EV_CHARGER)[0])
            self.ev_config_mode = user_input.get(CONF_EV_CONFIG_MODE, CONFIG_MODE_MANUAL)

            if self.ev_config_mode == CONFIG_MODE_SOLARMAN:
                return await self.async_step_ev_prefix()
            else:
                return await self.async_step_entities_ev_charger()

        schema = vol.Schema({
            vol.Required(CONF_EV_CONFIG_MODE, default=CONFIG_MODE_SOLARMAN): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": CONFIG_MODE_SOLARMAN, "label": "Prefix (automatyczne mapowanie)"},
                        {"value": CONFIG_MODE_MANUAL, "label": "Ręczne mapowanie encji"},
                    ],
                    mode=SelectSelectorMode.LIST,
                )
            ),
        })

        return self.async_show_form(
            step_id="ev_choose_mode",
            data_schema=schema,
        )

    async def async_step_ev_prefix(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Pobierz prefix OCPP (Charge Point ID) i zbuduj mapowanie encji ładowarki."""
        errors: dict[str, str] = {}

        if user_input is not None:
            prefix = user_input.get(CONF_EV_PREFIX, "").strip().lower()

            if not prefix:
                errors[CONF_EV_PREFIX] = "prefix_required"
            elif " " in prefix or not prefix.replace("_", "").isalnum():
                errors[CONF_EV_PREFIX] = "invalid_prefix"
            else:
                self.ev_prefix = prefix
                ev_profile = list_profiles(ROLE_EV_CHARGER)[0]
                self.entity_mapping.update(ev_profile.build_mapping(prefix))
                return self._create_entry()

        schema = vol.Schema({
            vol.Required(CONF_EV_PREFIX): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            ),
        })

        return self.async_show_form(
            step_id="ev_prefix",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_entities_ev_charger(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ręczne mapowanie encji ładowarki EV (gdy użytkownik nie chce trybu prefix)."""
        return await self._async_step_entities("ev_charger", None, user_input)

    def _create_entry(self) -> FlowResult:
        """Zapisz finalny wpis konfiguracji — wszystkie zebrane wartości w jednym entry.data."""
        title = "Solar Accelerator"
        if self.config_mode != CONFIG_MODE_MANUAL and self.solarman_prefix:
            title = f"Solar Accelerator ({self.solarman_prefix})"

        return self.async_create_entry(
            title=title,
            data={
                CONF_API_KEY: self.api_key,
                CONF_SERVER_URL: self.server_url,
                CONF_CONFIG_MODE: self.config_mode,
                CONF_SOLARMAN_PREFIX: self.solarman_prefix,
                CONF_INVERTER_MANUFACTURER: self.inverter_manufacturer,
                CONF_INVERTER_MODEL: self.inverter_model,
                CONF_EV_ENABLED: self.ev_enabled,
                CONF_EV_CONFIG_MODE: self.ev_config_mode,
                CONF_EV_PREFIX: self.ev_prefix,
                CONF_EV_MODEL: self.ev_model,
                CONF_ENTITY_MAPPING: self.entity_mapping,
            },
        )


class SolarAcceleratorOptionsFlow(config_entries.OptionsFlow):
    """Options flow — dynamiczne zarządzanie udostępnianymi (sterowalnymi) encjami.

    Dostępny przez przycisk „Konfiguruj" na karcie integracji. Pozwala dodawać i
    kasować dodatkowe urządzenia (ładowarka EV, CWU, pompa…), które integracja
    udostępnia serwisowi jako sterowalne odbiorniki. Lista trafia do
    ``entry.options[CONF_CONTROLLABLE_DEVICES]`` i jest dosyłana w paczce danych
    (``controllable_devices[]`` — patrz ``api.py``).

    Nie ustawiamy ``self.config_entry`` (deprecation w nowszych HA) — trzymamy
    własną referencję ``self._entry``.
    """

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry
        self._devices: list[dict[str, Any]] = list(
            config_entry.options.get(CONF_CONTROLLABLE_DEVICES, [])
        )
        # Szkic profilu (kreator "Zgłoś / eksportuj profil") — wczytaj, by edycja wznawiała.
        self._profile: dict[str, Any] = dict(config_entry.options.get(CONF_PROFILE_DRAFT, {}))

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Menu: sterowalne odbiorniki + kreator zgłoszenia profilu. Każda akcja zapisuje
        od razu (jak config flow), więc nic nie ginie po zamknięciu okna."""
        menu_options = ["add_device"]
        if self._devices:
            menu_options.append("remove_device")
        menu_options.append("export_profile")

        return self.async_show_menu(
            step_id="init",
            menu_options=menu_options,
            description_placeholders={"count": str(len(self._devices))},
        )

    def _persist(self) -> FlowResult:
        """Persystuj WSZYSTKIE opcje (odbiorniki + szkic profilu) i zakończ flow.

        Scalamy, bo ``async_create_entry`` w options flow zastępuje całe ``entry.options`` —
        bez scalania zapis odbiorników kasowałby szkic profilu i odwrotnie.
        """
        data = dict(self._entry.options)
        data[CONF_CONTROLLABLE_DEVICES] = self._devices
        if self._profile:
            data[CONF_PROFILE_DRAFT] = self._profile
        return self.async_create_entry(title="", data=data)

    def _save(self) -> FlowResult:
        """Alias zgodności — całość zapisu idzie przez ``_persist``."""
        return self._persist()

    async def async_step_add_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Formularz dodania jednego sterowalnego odbiornika (encja switch + opcjonalne sensory)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            label = (user_input.get("label") or "").strip()
            switch_entity = user_input.get("switch_entity") or ""
            if not label:
                errors["label"] = "label_required"
            elif not switch_entity:
                errors["switch_entity"] = "entity_required"

            if not errors:
                key = slugify(label) or slugify(switch_entity)
                device = {
                    "key": key,
                    "label": label,
                    "device_type": user_input.get("device_type", "other"),
                    "switch_entity": switch_entity,
                    "power_sensor": user_input.get("power_sensor") or None,
                    "energy_sensor": user_input.get("energy_sensor") or None,
                    "status_entity": user_input.get("status_entity") or None,
                    "nominal_power_w": user_input.get("nominal_power_w"),
                }
                # Nadpisz istniejący o tym samym kluczu (edycja), inaczej dodaj.
                self._devices = [d for d in self._devices if d.get("key") != key]
                self._devices.append(device)
                return self._save()  # zapis natychmiastowy

        schema = vol.Schema({
            vol.Required("label"): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
            vol.Required("device_type", default="other"): SelectSelector(
                SelectSelectorConfig(options=CONTROLLABLE_DEVICE_TYPES, mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Required("switch_entity"): EntitySelector(
                EntitySelectorConfig(domain=["switch", "input_boolean"])
            ),
            vol.Optional("power_sensor"): EntitySelector(
                EntitySelectorConfig(domain=["sensor"])
            ),
            vol.Optional("energy_sensor"): EntitySelector(
                EntitySelectorConfig(domain=["sensor"])
            ),
            vol.Optional("status_entity"): EntitySelector(
                EntitySelectorConfig(domain=["sensor", "binary_sensor"])
            ),
            vol.Optional("nominal_power_w"): NumberSelector(
                NumberSelectorConfig(min=0, max=50000, step=10, mode=NumberSelectorMode.BOX)
            ),
        })

        return self.async_show_form(step_id="add_device", data_schema=schema, errors=errors)

    async def async_step_remove_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Usuń zaznaczone urządzenia z listy."""
        if user_input is not None:
            to_remove = set(user_input.get("remove", []))
            self._devices = [d for d in self._devices if d.get("key") not in to_remove]
            return self._save()  # zapis natychmiastowy

        options = [
            {"value": d.get("key"), "label": f'{d.get("label")} ({d.get("switch_entity")})'}
            for d in self._devices
        ]
        schema = vol.Schema({
            vol.Required("remove", default=[]): SelectSelector(
                SelectSelectorConfig(options=options, multiple=True, mode=SelectSelectorMode.LIST)
            ),
        })

        return self.async_show_form(step_id="remove_device", data_schema=schema)

    # === Kreator "Zgłoś / eksportuj profil" ===

    def _read_mapping(self) -> dict[str, str]:
        """Mapowanie odczytu z konfiguracji, ograniczone do kluczy właściwych dla źródła."""
        mapping = self._entry.data.get(CONF_ENTITY_MAPPING, {})
        keys = set(EV_ENTITY_KEYS) if self._profile.get("source") == "ocpp" else set(INVERTER_KEYS)
        return {k: v for k, v in mapping.items() if k in keys}

    def _draft_preview(self) -> dict[str, Any]:
        """Zbuduj podgląd szkicu profilu z bieżącego stanu kreatora."""
        return build_profile_draft(
            manufacturer=self._profile.get("manufacturer", ""),
            model=self._profile.get("model", ""),
            source=self._profile.get("source", ""),
            prefix=self._profile.get("prefix", ""),
            read_mapping=self._read_mapping(),
            control_mapping=self._profile.get("control_mapping", {}),
            capabilities=self._profile.get("capabilities", {}),
        )

    async def async_step_export_profile(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Krok 1 kreatora: metadane urządzenia (producent, model, źródło, prefiks)."""
        mapping = self._entry.data.get(CONF_ENTITY_MAPPING, {})

        if user_input is not None:
            self._profile["manufacturer"] = (user_input.get("manufacturer") or "").strip()
            self._profile["model"] = (user_input.get("model") or "").strip()
            # Źródło to nowy slug podany przez użytkownika — czyścimy go do bezpiecznej postaci.
            self._profile["source"] = slugify(user_input.get("source") or "")
            self._profile["prefix"] = (user_input.get("prefix") or "").strip().lower()
            return await self.async_step_profile_capabilities()

        selected = get_profile(self._entry.data.get(CONF_CONFIG_MODE, ""))
        default_source = self._profile.get("source") or (selected.source if selected else "")
        default_manufacturer = (
            self._profile.get("manufacturer")
            or self._entry.data.get(CONF_INVERTER_MANUFACTURER)
            or (selected.manufacturer if selected else "")
        )
        default_model = (
            self._profile.get("model")
            or self._entry.data.get(CONF_INVERTER_MODEL)
            or (selected.model if selected else "")
        )
        default_prefix = (
            self._profile.get("prefix")
            or self._entry.data.get(CONF_SOLARMAN_PREFIX)
            or detect_prefix(list(mapping.values()))
        )

        schema = vol.Schema({
            vol.Required("manufacturer", default=default_manufacturer): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            ),
            vol.Required("model", default=default_model): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            ),
            vol.Required("source", default=default_source): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            ),
            vol.Required("prefix", default=default_prefix): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            ),
        })

        return self.async_show_form(step_id="export_profile", data_schema=schema)

    async def async_step_profile_capabilities(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Krok 2: capabilities (pole działania) — co falownik potrafi."""
        current = self._profile.get("capabilities", {})

        if user_input is not None:
            self._profile["capabilities"] = {
                key: bool(user_input.get(key, False)) for key, _label in contract.CAPABILITIES
            }
            return await self.async_step_control_inverter()

        schema = vol.Schema({
            vol.Required(key, default=bool(current.get(key, False))): bool
            for key, _label in contract.CAPABILITIES
        })

        return self.async_show_form(step_id="profile_capabilities", data_schema=schema)

    async def _async_step_control(
        self, category: str, next_step: str, user_input: dict[str, Any] | None
    ) -> FlowResult:
        """Wspólna obsługa kroków mapowania encji sterujących (wszystkie pola opcjonalne).

        Selektor pokazuje encje wielu typów (sterowanie bywa wystawione jako number/
        select/switch/time itd. zależnie od integracji) — kodek dobierze się później ze
        snapshotu. Dla TOU pytamy tylko o slot 1; sloty 2–6 generuje skrypt z wzorca.
        """
        controls = contract.controls_for_category(category)
        if category == "schedule":
            controls = [c for c in controls if c[0].startswith("tou_1_")]
        current: dict[str, str] = dict(self._profile.get("control_mapping", {}))

        if user_input is not None:
            for key, _label, _vt, _cat in controls:
                value = user_input.get(key)
                if value:
                    current[key] = value
                else:
                    current.pop(key, None)
            self._profile["control_mapping"] = current
            return await getattr(self, f"async_step_{next_step}")()

        schema_dict: dict[Any, Any] = {}
        for key, _label, _vt, _cat in controls:
            default = current.get(key, vol.UNDEFINED)
            schema_dict[vol.Optional(key, default=default)] = EntitySelector(
                EntitySelectorConfig(domain=CONTROL_ENTITY_DOMAINS)
            )

        return self.async_show_form(
            step_id=f"control_{category}",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={"category_name": contract.CONTROL_CATEGORIES.get(category, category)},
        )

    async def async_step_control_inverter(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self._async_step_control("inverter", "control_battery", user_input)

    async def async_step_control_battery(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self._async_step_control("battery", "control_grid", user_input)

    async def async_step_control_grid(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self._async_step_control("grid", "control_pv", user_input)

    async def async_step_control_pv(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self._async_step_control("pv", "control_schedule", user_input)

    async def async_step_control_schedule(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self._async_step_control("schedule", "control_extra", user_input)

    async def async_step_control_extra(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Dodatkowe encje sterujące spoza knobów (np. drugi switch fan-outu)."""
        if user_input is not None:
            self._profile["control_extra"] = user_input.get("control_extra", []) or []
            return await self.async_step_profile_summary()

        default = self._profile.get("control_extra", [])
        schema = vol.Schema({
            vol.Optional("control_extra", default=default): EntitySelector(
                EntitySelectorConfig(domain=CONTROL_ENTITY_DOMAINS, multiple=True)
            ),
        })
        return self.async_show_form(step_id="control_extra", data_schema=schema)

    async def async_step_profile_summary(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Krok końcowy: podsumowanie i zapis szkicu. Eksport przez 'Pobierz diagnostykę'."""
        if user_input is not None:
            return self._persist()

        draft = self._draft_preview()
        return self.async_show_form(
            step_id="profile_summary",
            data_schema=vol.Schema({}),
            description_placeholders={
                "file_path": draft["file_path"],
                "read_count": str(len(draft["read_template"])),
                "control_count": str(len(draft["control_template"])),
                "literal_count": str(len(draft["literal_entities"])),
            },
        )
