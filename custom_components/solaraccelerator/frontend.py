"""Wsparcie kart Lovelace Solar Accelerator.

Dwie odpowiedzialności:

1. **Proxy danych** (`SolarAcceleratorChartView`) — endpoint na serwerze HA, do
   którego uderza karta (same-origin, auth sesją HA). Proxy dokłada
   ``Authorization: Bearer <api_key>`` z konfiguracji integracji i woła backend.
   Klucz API NIGDY nie trafia do przeglądarki.

2. **Bundel karty serwowany LOKALNIE z HA** — integracja pobiera ``sa-chart.js``
   z backendu *server-side* (HA → backend), zapisuje w cache i serwuje przez
   statyczną ścieżkę HA. Dzięki temu przeglądarka ładuje JS z tego samego hosta
   co reszta HA — działa nawet gdy sieć przeglądarki (np. firmowa) blokuje domenę
   backendu. Dane i tak idą przez proxy (server-side), więc jedyna zależność od
   backendu jest po stronie serwera HA, nie przeglądarki. Fallback: gdy backend
   nieosiągalny przy starcie, serwujemy ostatni zapisany bundel.

Bezpieczeństwo proxy (świadome decyzje):
- ``requires_auth = True`` (domyślne w HomeAssistantView) — tylko zalogowany user HA.
- **Sztywna allowlista** nazwa→ścieżka (``_CHART_ENDPOINTS``) — NIE open-relay.
- Tylko GET, timeout, whitelist parametru ``period``.
"""
from __future__ import annotations

import asyncio
import logging
import os
from http import HTTPStatus

import aiohttp
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_API_KEY, CONF_SERVER_URL, DEFAULT_SERVER_URL, DOMAIN

LOGGER = logging.getLogger(__name__)

# Ścieżka bundla karty na backendzie (źródło do pobrania server-side).
# Statyk z public/ — Nitro serwuje go bezpośrednio, bez parsowania.
CARD_JS_BACKEND_PATH = "/ha-card/sa-chart.js"

# Lokalna ścieżka, pod którą HA serwuje bundel przeglądarce (same-origin).
CARD_LOCAL_URL = "/solaraccelerator_static/sa-chart.js"

# Plik cache w katalogu konfiguracji HA (config/solaraccelerator/sa-chart.js).
_CACHE_SUBDIR = "solaraccelerator"
_CACHE_FILENAME = "sa-chart.js"

# Allowlista: nazwa wykresu (z karty) -> read-only ścieżka na backendzie.
# KLUCZOWE: brak generycznego pass-through. Nowe wykresy = nowy wpis tutaj.
_CHART_ENDPOINTS: dict[str, str] = {
    "prices": "/api/homeassistant/price-series",
    "profit": "/api/homeassistant/profit-series",
    "plan": "/api/homeassistant/plan-series",
}

# Whitelist parametru period — nie forwardujemy dowolnego query do backendu.
_ALLOWED_PERIODS = {"today", "week", "month"}

# Flagi w hass.data — rejestrujemy raz, niezależnie od liczby config entries.
_VIEW_REGISTERED = f"{DOMAIN}_chart_view_registered"
_CARD_REGISTERED = f"{DOMAIN}_card_resource_registered"


class SolarAcceleratorChartView(HomeAssistantView):
    """Proxy GET dla danych wykresów kart Lovelace."""

    url = "/api/solaraccelerator/chart/{name}"
    name = "api:solaraccelerator:chart"

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    def _entry_config(self) -> dict | None:
        """Pierwsza skonfigurowana integracja z kluczem API (zwykle jedna)."""
        for value in self.hass.data.get(DOMAIN, {}).values():
            if isinstance(value, dict) and value.get(CONF_API_KEY):
                return value
        return None

    async def get(self, request, name: str):
        backend_path = _CHART_ENDPOINTS.get(name)
        if backend_path is None:
            return self.json_message("Nieznany wykres", HTTPStatus.NOT_FOUND)

        cfg = self._entry_config()
        if not cfg:
            return self.json_message("Integracja nieskonfigurowana", HTTPStatus.BAD_GATEWAY)

        api_key = cfg.get(CONF_API_KEY)
        server_url = cfg.get(CONF_SERVER_URL) or DEFAULT_SERVER_URL

        period = request.query.get("period", "today")
        if period not in _ALLOWED_PERIODS:
            period = "today"

        session = async_get_clientsession(self.hass)
        url = f"{server_url}{backend_path}"
        try:
            async with session.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                params={"period": period},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                # Backend zwraca czysty JSON również dla błędów — przepuszczamy status + body.
                try:
                    data = await resp.json()
                except (aiohttp.ContentTypeError, ValueError):
                    return self.json_message(
                        "Nieprawidłowa odpowiedź backendu", HTTPStatus.BAD_GATEWAY
                    )
                return self.json(data, status_code=resp.status)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            LOGGER.warning("Proxy wykresu '%s': błąd połączenia z backendem", name)
            return self.json_message("Błąd połączenia z backendem", HTTPStatus.BAD_GATEWAY)


def async_register_chart_view(hass: HomeAssistant) -> None:
    """Zarejestruj proxy danych (idempotentnie)."""
    if hass.data.get(_VIEW_REGISTERED):
        return
    hass.http.register_view(SolarAcceleratorChartView(hass))
    hass.data[_VIEW_REGISTERED] = True


async def _refresh_card_bundle(hass: HomeAssistant, server_url: str, cache_file: str) -> None:
    """Pobierz bundel karty z backendu (server-side) i zapisz w cache.

    Przy niepowodzeniu zostaje ostatni zapisany plik (fallback), więc karta
    działa nawet gdy backend jest chwilowo nieosiągalny.
    """
    url = f"{server_url.rstrip('/')}{CARD_JS_BACKEND_PATH}"
    session = async_get_clientsession(hass)
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
            content = await resp.read()
    except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as err:
        LOGGER.warning(
            "Nie pobrano bundla karty z %s (%s) — używam cache jeśli istnieje", url, err
        )
        return

    def _write() -> None:
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        tmp = f"{cache_file}.tmp"
        with open(tmp, "wb") as fh:
            fh.write(content)
        os.replace(tmp, cache_file)

    await hass.async_add_executor_job(_write)
    LOGGER.info("Pobrano bundel karty (%d B) z backendu do cache", len(content))


async def async_setup_card(hass: HomeAssistant, server_url: str, version: str) -> None:
    """Odśwież bundel z backendu i wystaw go LOKALNIE z HA (idempotentnie).

    Przeglądarka ładuje JS z tego samego hosta co HA — niezależnie od tego, czy
    jej sieć dosięga domeny backendu.
    """
    cache_file = hass.config.path(_CACHE_SUBDIR, _CACHE_FILENAME)

    # Odśwież cache przy każdym setupie (auto-update z backendu, server-side).
    await _refresh_card_bundle(hass, server_url, cache_file)

    # Statyk + zasób rejestrujemy tylko raz.
    if hass.data.get(_CARD_REGISTERED):
        return

    if not await hass.async_add_executor_job(os.path.exists, cache_file):
        LOGGER.warning(
            "Bundel karty niedostępny (backend nieosiągalny i brak cache) — "
            "karta pominięta, spróbuję ponownie przy następnym starcie"
        )
        return

    # Serwuj plik z cache pod lokalnym URL HA (bez auth — to publiczny JS bez sekretów).
    await _register_static(hass, cache_file)

    from homeassistant.components.frontend import add_extra_js_url

    add_extra_js_url(hass, f"{CARD_LOCAL_URL}?v={version}")
    hass.data[_CARD_REGISTERED] = True
    LOGGER.info("Karta Lovelace Solar Accelerator serwowana lokalnie z HA: %s", CARD_LOCAL_URL)


async def _register_static(hass: HomeAssistant, cache_file: str) -> None:
    """Zarejestruj statyczną ścieżkę (nowe async API, fallback na starsze sync)."""
    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_LOCAL_URL, cache_file, True)]
        )
    except (ImportError, AttributeError):
        # Starsze HA — deprecated sync API.
        hass.http.register_static_path(CARD_LOCAL_URL, cache_file, True)
