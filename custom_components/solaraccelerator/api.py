"""Klient HTTP do komunikacji z backendem Solar Accelerator.

Plik zawiera wyłącznie funkcje wykonujące zapytania do API serwera:
- ``async_send_data``        — pełna paczka godzinowa,
- ``async_fetch_prices``     — pobranie cen energii,
- ``async_fetch_profit``     — pobranie wyliczonego zysku dziennego,
- ``async_check_data_ready`` — odpytanie czy serwer przetworzył paczkę,
- ``async_send_live_data``   — szybki push stanu i odbiór komend,
- ``async_ack_command``      — potwierdzenie wykonania komendy.

Wszystkie funkcje używają wspólnej sesji aiohttp HA i tego samego nagłówka
``Authorization: Bearer <api_key>``. Stan połączenia oraz znaczniki czasu zapisywane
są w ``coordinator_data`` — to ten słownik czytają później sensory diagnostyczne.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import (
    CONF_API_KEY,
    CONF_ENTITY_MAPPING,
    CONF_EV_ENABLED,
    CONF_EV_PREFIX,
    CONF_SERVER_URL,
    CONF_SOLARMAN_PREFIX,
    CONF_CONTROLLABLE_DEVICES,
    API_COMMAND_ACK_ENDPOINT,
    API_DATA_READY_ENDPOINT,
    API_LIVE_ENDPOINT,
    API_PRICES_ENDPOINT,
    API_PROFIT_ENDPOINT,
    API_SEND_DATA_ENDPOINT,
    EV_ENTITY_KEYS,
    INVERTER_KEYS,
)
from .helpers import convert_value

_LOGGER = logging.getLogger(__name__)


def _build_entities_payload(
    hass: HomeAssistant,
    coordinator_data: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], int, bool]:
    """Zbierz aktualne stany encji HA i zwróć dane dla falownika oraz ładowarki EV.

    Iterujemy po wszystkich kluczach zdefiniowanych w stałych (INVERTER_KEYS, EV_ENTITY_KEYS)
    i dla każdego pobieramy stan z HA przez ``hass.states.get``. Gdy encja nie jest
    zmapowana albo nie istnieje — wpisujemy 0, żeby payload miał zawsze ten sam kształt.

    Encje EV są zbierane tylko gdy użytkownik włączył ładowarkę w config flow
    i podał prefix (oba warunki musi spełnić — sam toggle bez prefixu nie wystarczy).

    Zwraca: ``(inverter_data, ev_data, entities_count, ev_enabled)``.
    """
    entity_mapping = coordinator_data.get(CONF_ENTITY_MAPPING, {})
    ev_enabled = bool(
        coordinator_data.get(CONF_EV_ENABLED)
        and coordinator_data.get(CONF_EV_PREFIX)
    )

    inverter_data: dict[str, Any] = {}
    ev_data: dict[str, Any] = {}
    entities_count = 0

    for entity_key in INVERTER_KEYS:
        ha_entity_id = entity_mapping.get(entity_key)
        if ha_entity_id:
            state = hass.states.get(ha_entity_id)
            if state:
                inverter_data[entity_key] = convert_value(state.state, entity_key)
                entities_count += 1
            else:
                inverter_data[entity_key] = 0
        else:
            inverter_data[entity_key] = 0

    if ev_enabled:
        for entity_key in EV_ENTITY_KEYS:
            ha_entity_id = entity_mapping.get(entity_key)
            if ha_entity_id:
                state = hass.states.get(ha_entity_id)
                if state:
                    ev_data[entity_key] = convert_value(state.state, entity_key)
                    entities_count += 1
                else:
                    ev_data[entity_key] = 0
            else:
                ev_data[entity_key] = 0

    return inverter_data, ev_data, entities_count, ev_enabled


def _build_full_payload(
    hass: HomeAssistant,
    coordinator_data: dict[str, Any],
) -> tuple[dict[str, Any], int, bool]:
    """Zbuduj pełen payload requestu (timestamp + status komunikacji + encje + prefiksy).

    Wcześniej tę samą logikę miały zduplikowaną ``async_send_data`` i ``async_send_live_data``;
    teraz obie korzystają z tego helpera, żeby format payloadu był spójny.

    Zawsze dołączamy ``inverterOnline`` (status łącza falownik↔HA, ustawiany przez
    ``health.update_inverter_health`` w pętli live). Gdy falownik jest **offline**,
    NIE dołączamy wartości encji — leci sam status, żeby backend nie dostał zer
    psujących wykresy/statystyki.

    Zwraca: ``(payload, entities_count, ev_enabled)``.
    """
    online = bool(coordinator_data.get("inverter_online", True))

    payload: dict[str, Any] = {
        "timestamp": dt_util.utcnow().isoformat(),
        "inverterPrefix": coordinator_data.get(CONF_SOLARMAN_PREFIX, ""),
        "inverterOnline": online,
    }

    if not online:
        # Falownik offline — sam status, bez wartości encji (patrz docstring).
        return payload, 0, False

    inverter_data, ev_data, entities_count, ev_enabled = _build_entities_payload(
        hass, coordinator_data
    )

    entities_payload: dict[str, Any] = {"inverter": inverter_data}
    if ev_enabled and ev_data:
        entities_payload["ev_charger"] = ev_data

    payload["entities"] = entities_payload
    if ev_enabled:
        payload["evPrefix"] = coordinator_data.get(CONF_EV_PREFIX, "")

    # Custom sterowalne odbiorniki (OptionsFlow → entry.options). Wysyłamy definicje
    # (encje + typ) jako discovery — backend mapuje je na katalog urządzeń
    # (metadata.additionalDevices). Dorzucamy też bieżący stan switcha, gdy dostępny.
    controllable = _build_controllable_payload(hass, coordinator_data)
    if controllable:
        payload["controllable_devices"] = controllable

    return payload, entities_count, ev_enabled


def _build_controllable_payload(
    hass: HomeAssistant,
    coordinator_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Zbierz definicje custom sterowalnych odbiorników + bieżący stan ich encji.

    Lista pochodzi z OptionsFlow (``CONF_CONTROLLABLE_DEVICES``). Każdy wpis to
    definicja (key/label/device_type + encje), wzbogacona o ``switch_state``
    (on/off) i — jeśli skonfigurowane — odczyty mocy/energii/statusu.
    """
    devices = coordinator_data.get(CONF_CONTROLLABLE_DEVICES) or []
    out: list[dict[str, Any]] = []

    for dev in devices:
        switch_entity = dev.get("switch_entity")
        switch_state = None
        if switch_entity and (st := hass.states.get(switch_entity)):
            switch_state = st.state

        entry: dict[str, Any] = {
            "key": dev.get("key"),
            "label": dev.get("label"),
            "device_type": dev.get("device_type", "other"),
            "switch_entity": switch_entity,
            "switch_state": switch_state,
            "power_sensor": dev.get("power_sensor"),
            "energy_sensor": dev.get("energy_sensor"),
            "status_entity": dev.get("status_entity"),
            "nominal_power_w": dev.get("nominal_power_w"),
        }

        for field, sensor_key in (("power_w", "power_sensor"), ("energy_kwh", "energy_sensor"), ("status", "status_entity")):
            sensor_id = dev.get(sensor_key)
            if sensor_id and (s := hass.states.get(sensor_id)):
                entry[field] = s.state

        out.append(entry)

    return out


async def async_send_data(
    hass: HomeAssistant,
    coordinator_data: dict[str, Any],
) -> bool:
    """Wyślij pełną paczkę danych do backendu (endpoint godzinowy).

    Funkcja aktualizuje pola w ``coordinator_data``:
    - ``connection_status``  — ``connected`` / ``auth_error`` / ``error`` / ``disconnected``,
    - ``last_sent``          — timestamp ostatniej udanej wysyłki,
    - ``last_response``      — krótki komunikat (OK lub fragment błędu),
    - ``entities_sent``      — liczba encji które miały stan przy ostatniej wysyłce.

    Zwraca ``True`` tylko gdy serwer odpowiedział 200. Każdy inny status oraz każdy
    wyjątek sieciowy jest logowany i powoduje ``return False`` — wtedy pętla
    godzinowa pomija krok pollingowania ``data-ready`` i fetchowania profitu.
    """
    api_key = coordinator_data.get(CONF_API_KEY)
    server_url = coordinator_data.get(CONF_SERVER_URL)

    session = async_get_clientsession(hass)
    endpoint = f"{server_url}{API_SEND_DATA_ENDPOINT}"

    try:
        payload, entities_count, _ = _build_full_payload(hass, coordinator_data)

        async with session.post(
            endpoint,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            response_text = await resp.text()

            if resp.status == 200:
                coordinator_data["last_sent"] = dt_util.now().strftime("%Y-%m-%d %H:%M:%S")
                coordinator_data["connection_status"] = "connected"
                coordinator_data["entities_sent"] = entities_count
                coordinator_data["last_response"] = "OK"
                _LOGGER.info(
                    "Dane wysłane pomyślnie do %s: %d encji",
                    endpoint,
                    entities_count,
                )
                return True
            elif resp.status == 401:
                coordinator_data["connection_status"] = "auth_error"
                coordinator_data["last_response"] = "Nieprawidłowy klucz API"
                _LOGGER.error("Błąd autoryzacji: nieprawidłowy klucz API")
            else:
                coordinator_data["connection_status"] = "error"
                coordinator_data["last_response"] = f"HTTP {resp.status}: {response_text[:100]}"
                _LOGGER.error(
                    "Nie udało się wysłać danych: %s - %s",
                    resp.status,
                    response_text,
                )

    except aiohttp.ClientError as e:
        coordinator_data["connection_status"] = "disconnected"
        coordinator_data["last_response"] = f"Connection error: {str(e)[:50]}"
        _LOGGER.error("Błąd połączenia: %s", e)
    except Exception as e:
        coordinator_data["connection_status"] = "error"
        coordinator_data["last_response"] = f"Error: {str(e)[:50]}"
        _LOGGER.exception("Błąd podczas wysyłania danych: %s", e)

    return False


async def async_fetch_prices(
    hass: HomeAssistant,
    coordinator_data: dict[str, Any],
) -> bool:
    """Pobierz aktualne ceny energii (zakup + sprzedaż) z backendu.

    Wynik trafia do ``coordinator_data["prices"]`` jako słownik z pełnym kompletem
    pól (current/min/max/average dla obu kierunków + flagi tania/droga + provider).
    Sensory cenowe czytają stąd dane przy każdym odświeżeniu encji.

    Zwraca ``True`` przy odpowiedzi 200. Status 404 (serwer nie ma jeszcze cen na dziś)
    jest tylko logowany — nie zmieniamy starych wartości, żeby sensory nie nullowały się
    między aktualizacjami.
    """
    api_key = coordinator_data.get(CONF_API_KEY)
    server_url = coordinator_data.get(CONF_SERVER_URL)

    session = async_get_clientsession(hass)
    endpoint = f"{server_url}{API_PRICES_ENDPOINT}"

    try:
        async with session.get(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                coordinator_data["prices"] = {
                    # Ceny zakupu energii (kupno z sieci)
                    "current_buy_price": data.get("current_buy_price"),
                    "min_buy_price": data.get("min_buy_price"),
                    "max_buy_price": data.get("max_buy_price"),
                    "average_buy_price": data.get("average_buy_price"),
                    # Ceny sprzedaży energii (oddawanie do sieci)
                    "current_sell_price": data.get("current_sell_price"),
                    "min_sell_price": data.get("min_sell_price"),
                    "max_sell_price": data.get("max_sell_price"),
                    "average_sell_price": data.get("average_sell_price"),
                    # Metadane: waluta, jednostka, znaczniki tania/droga, provider, czas aktualizacji
                    "currency": data.get("currency"),
                    "unit": data.get("unit"),
                    "current_hour": data.get("current_hour"),
                    "is_cheap": data.get("is_cheap"),
                    "is_expensive": data.get("is_expensive"),
                    "provider": data.get("provider"),
                    "updated_at": data.get("updated_at"),
                }
                coordinator_data["prices_last_update"] = dt_util.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                _LOGGER.info("Pobrano ceny energii z %s", endpoint)
                return True
            elif resp.status == 404:
                _LOGGER.warning("Brak dostępnych cen energii: %s", await resp.text())
            else:
                _LOGGER.error("Nie udało się pobrać cen: %s", resp.status)

    except aiohttp.ClientError as e:
        _LOGGER.error("Błąd połączenia podczas pobierania cen: %s", e)
    except Exception as e:
        _LOGGER.exception("Błąd podczas pobierania cen: %s", e)

    return False


async def async_fetch_profit(
    hass: HomeAssistant,
    coordinator_data: dict[str, Any],
) -> bool:
    """Pobierz dzienny bilans finansowy instalacji PV z backendu.

    Backend liczy zysk po przetworzeniu paczki godzinowej — dlatego pętla godzinowa
    najpierw wywołuje ``async_send_data``, potem czeka aż ``async_check_data_ready``
    zwróci ``True``, a dopiero potem fetchuje profit.

    Zapisuje dane do ``coordinator_data["profit"]`` — używają ich sensory:
    daily_profit, battery_value, battery_avg_price.
    """
    api_key = coordinator_data.get(CONF_API_KEY)
    server_url = coordinator_data.get(CONF_SERVER_URL)

    session = async_get_clientsession(hass)
    endpoint = f"{server_url}{API_PROFIT_ENDPOINT}"

    try:
        async with session.get(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                coordinator_data["profit"] = {
                    "date": data.get("date"),
                    "daily_profit_pln": data.get("daily_profit_pln"),
                    "battery_value_pln": data.get("battery_value_pln"),
                    "battery_avg_price_pln": data.get("battery_avg_price_pln"),
                    "currency": data.get("currency"),
                }
                coordinator_data["profit_last_update"] = dt_util.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                _LOGGER.info("Pobrano dane o zysku z %s", endpoint)
                return True
            elif resp.status == 404:
                _LOGGER.warning("Brak danych o zysku: %s", await resp.text())
            else:
                _LOGGER.error("Nie udało się pobrać zysku: %s", resp.status)

    except aiohttp.ClientError as e:
        _LOGGER.error("Błąd połączenia podczas pobierania zysku: %s", e)
    except Exception as e:
        _LOGGER.exception("Błąd podczas pobierania zysku: %s", e)

    return False


async def async_check_data_ready(
    hass: HomeAssistant,
    coordinator_data: dict[str, Any],
) -> bool:
    """Sprawdź czy backend zakończył przetwarzanie ostatniej paczki godzinowej.

    Endpoint zwraca ``{"ready": true|false}``. Pętla godzinowa pollinguje to co 10s
    przez maksymalnie 30 prób (czyli ~5 minut), żeby nie pobierać profitu z nieaktualną
    paczką.
    """
    api_key = coordinator_data.get(CONF_API_KEY)
    server_url = coordinator_data.get(CONF_SERVER_URL)

    session = async_get_clientsession(hass)
    endpoint = f"{server_url}{API_DATA_READY_ENDPOINT}"

    try:
        async with session.get(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                is_ready = data.get("ready", False)
                _LOGGER.debug("Sprawdzenie data-ready: %s", is_ready)
                return is_ready
            else:
                _LOGGER.warning("Sprawdzenie data-ready nieudane: %s", resp.status)
                return False

    except aiohttp.ClientError as e:
        _LOGGER.error("Błąd połączenia przy sprawdzaniu data-ready: %s", e)
    except Exception as e:
        _LOGGER.exception("Błąd przy sprawdzaniu data-ready: %s", e)

    return False


async def async_send_live_data(
    hass: HomeAssistant,
    coordinator_data: dict[str, Any],
) -> tuple[str, int | None, int | None, list[dict[str, Any]]]:
    """Wyślij szybki push stanu na endpoint ``/api/homeassistant/live``.

    To jest główny kanał komunikacji z serwerem między pełnymi godzinami:
    klient pcha aktualny stan, a serwer w odpowiedzi może zwrócić listę komend
    do wykonania (``pending_commands``) — np. zmiana parametru falownika.

    Interwał między pushami ustala serwer (pole ``live_interval_seconds``); klient
    aktualizuje swój interwał zarówno gdy serwer odpowiedział 200 jak i 429.
    Dzięki temu po rate limicie nie utykamy w pętli za szybkich pushów.

    Zwraca krotkę: ``(status, live_interval_seconds, retry_after_seconds, pending_commands)``,
    gdzie ``status`` to:
        ``ok``           — wszystko OK, można wykonać komendy,
        ``disabled``     — kanał wyłączony przez admina (HTTP 503),
        ``rate_limited`` — za szybko (HTTP 429),
        ``auth_error``   — zły klucz API (HTTP 401),
        ``error``        — inny błąd (timeout, network, 5xx).

    Lista ``pending_commands`` jest niepusta tylko gdy ``status == "ok"``.
    """
    api_key = coordinator_data.get(CONF_API_KEY)
    server_url = coordinator_data.get(CONF_SERVER_URL)

    session = async_get_clientsession(hass)
    endpoint = f"{server_url}{API_LIVE_ENDPOINT}"

    try:
        payload, _, _ = _build_full_payload(hass, coordinator_data)

        async with session.post(
            endpoint,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                live_interval = data.get("live_interval_seconds")
                coordinator_data["live_status"] = "live"
                coordinator_data["live_last_push"] = dt_util.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                if live_interval:
                    coordinator_data["live_interval_seconds"] = live_interval
                pending_commands = data.get("pending_commands", []) or []
                _LOGGER.debug(
                    "Live push OK: %d encji, %d komend do wykonania",
                    data.get("entitiesReceived", 0),
                    len(pending_commands),
                )
                return ("ok", live_interval, None, pending_commands)

            elif resp.status == 503:
                coordinator_data["live_status"] = "disabled"
                _LOGGER.debug("Kanał live wyłączony na serwerze (503)")
                return ("disabled", None, None, [])

            elif resp.status == 429:
                coordinator_data["live_status"] = "rate_limited"
                retry_after = int(resp.headers.get("Retry-After", "5"))
                # Serwer może zwrócić nowy interwał w body również przy 429 —
                # czytamy go, żeby od razu zsynchronizować klienta z nowym rytmem
                # zamiast utykać w pętli rate limitu
                live_interval = None
                try:
                    data = await resp.json()
                    if server_iv := data.get("live_interval_seconds"):
                        live_interval = server_iv
                        coordinator_data["live_interval_seconds"] = server_iv
                except Exception:
                    pass
                _LOGGER.debug(
                    "Rate limit: retry za %ds, interwał serwera=%s",
                    retry_after, live_interval,
                )
                return ("rate_limited", live_interval, retry_after, [])

            elif resp.status == 401:
                coordinator_data["live_status"] = "auth_error"
                _LOGGER.error("Live push: nieprawidłowy klucz API (401)")
                return ("auth_error", None, None, [])

            else:
                coordinator_data["live_status"] = "error"
                text = await resp.text()
                _LOGGER.error("Live push nieudany: %s - %s", resp.status, text[:100])
                return ("error", None, None, [])

    except asyncio.TimeoutError:
        coordinator_data["live_status"] = "error"
        _LOGGER.warning("Live push: timeout")
        return ("error", None, None, [])
    except aiohttp.ClientError as e:
        coordinator_data["live_status"] = "error"
        _LOGGER.warning("Live push: błąd połączenia: %s", e)
        return ("error", None, None, [])
    except Exception as e:
        coordinator_data["live_status"] = "error"
        _LOGGER.exception("Live push: nieoczekiwany błąd: %s", e)
        return ("error", None, None, [])


async def async_ack_command(
    hass: HomeAssistant,
    coordinator_data: dict[str, Any],
    cmd_id: str,
    success: bool,
    error: str | None,
) -> None:
    """Potwierdź serwerowi wykonanie komendy (ACK).

    Wysyłane zawsze — niezależnie od tego czy komenda się udała czy nie. Backend
    używa ACK żeby usunąć komendę z kolejki ``pending_commands`` i wiedzieć, że
    nie musi jej ponawiać przy kolejnym live push.

    Brak ACK = serwer poda tę samą komendę ponownie. Dlatego błędy sieciowe tutaj
    tylko logujemy — nie ponawiamy, bo komenda i tak wróci przy następnym pushu.
    """
    api_key = coordinator_data.get(CONF_API_KEY)
    server_url = coordinator_data.get(CONF_SERVER_URL)
    session = async_get_clientsession(hass)
    endpoint = f"{server_url}{API_COMMAND_ACK_ENDPOINT.replace('{id}', cmd_id)}"

    try:
        async with session.post(
            endpoint,
            json={"success": success, "error": error},
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                _LOGGER.warning(
                    "ACK dla %s nieudany: %s - %s",
                    cmd_id, resp.status, text[:100],
                )
            else:
                _LOGGER.debug("ACK dla %s wysłany (success=%s)", cmd_id, success)
    except Exception as e:
        _LOGGER.warning("ACK dla %s: błąd połączenia: %s", cmd_id, e)
