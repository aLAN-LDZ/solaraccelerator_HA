"""Pętle w tle uruchamiane przez integrację.

Dwa niezależne taski (oba startowane w ``sensor.py``):

1. ``async_send_data_hourly`` — czeka do najbliższej pełnej godziny, wysyła pełną
   paczkę danych, fetchuje ceny, a po potwierdzeniu data-ready także zysk dzienny.

2. ``async_send_live_data_loop`` — szybki push co kilkanaście sekund (interwał ustawia
   serwer). Odbiera komendy od backendu i wykonuje je przez dispatcher.

Obie pętle są odporne na wyjątki — w bloku ``except Exception`` logują i kontynuują,
żeby pojedynczy błąd sieci nie zabijał taska.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import (
    async_check_data_ready,
    async_fetch_prices,
    async_fetch_profit,
    async_send_data,
    async_send_live_data,
)
from .const import (
    DEFAULT_LIVE_INTERVAL,
    LIVE_AUTH_RETRY,
    LIVE_DISABLED_RETRY,
)
from .helpers import get_next_full_hour, get_seconds_until_next_hour

_LOGGER = logging.getLogger(__name__)


async def async_send_data_hourly(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator_data: dict[str, Any],
) -> None:
    """Pętla wysyłająca pełną paczkę danych co pełną godzinę.

    Sekwencja w jednej iteracji:
        1. Oblicz ile zostało do następnej pełnej godziny i poczekaj.
        2. Wyślij paczkę (``async_send_data``) i równolegle pobierz ceny.
        3. Jeśli wysyłka się udała — pollinguj ``data-ready`` co 10s (max 30 prób).
        4. Po potwierdzeniu pobierz zaktualizowany zysk dzienny.

    Po pełnym cyklu pętla wraca na start i czeka do kolejnej pełnej godziny.
    """

    while True:
        try:
            seconds_to_wait = get_seconds_until_next_hour()
            next_scheduled = get_next_full_hour()
            coordinator_data["next_scheduled"] = next_scheduled.strftime("%Y-%m-%d %H:%M:%S")

            _LOGGER.debug(
                "Następna wysyłka zaplanowana na %s (za %.0f sekund)",
                next_scheduled,
                seconds_to_wait,
            )

            await asyncio.sleep(seconds_to_wait)

            # Krok 1: wyślij paczkę i od razu pobierz ceny (równolegle, bez czekania)
            send_success = await async_send_data(hass, coordinator_data)
            await async_fetch_prices(hass, coordinator_data)

            if send_success:
                # Krok 2: czekamy aż backend przetworzy paczkę (do ok. 5 minut)
                max_retries = 30
                retry_interval = 10  # sekund między próbami

                for attempt in range(max_retries):
                    is_ready = await async_check_data_ready(hass, coordinator_data)

                    if is_ready:
                        # Krok 3: dane gotowe — pobieramy zaktualizowany zysk
                        _LOGGER.info("Backend gotowy, pobieram dane o zysku")
                        await async_fetch_profit(hass, coordinator_data)
                        break

                    _LOGGER.debug(
                        "Backend jeszcze nie gotowy, próba %d/%d za %d sekund",
                        attempt + 1,
                        max_retries,
                        retry_interval,
                    )
                    await asyncio.sleep(retry_interval)
                else:
                    # Wyszliśmy z pętli przez ``range`` (brak break) — timeout
                    _LOGGER.warning(
                        "Timeout data-ready po %d próbach, pomijam aktualizację zysku",
                        max_retries,
                    )

        except asyncio.CancelledError:
            _LOGGER.debug("Pętla godzinowa anulowana")
            break
        except Exception as e:
            _LOGGER.exception("Błąd w pętli godzinowej: %s", e)
            # Po nieoczekiwanym błędzie odczekaj minutę przed kolejnym podejściem,
            # żeby nie zalewać serwera przy długotrwałej awarii
            await asyncio.sleep(60)


async def async_send_live_data_loop(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator_data: dict[str, Any],
) -> None:
    """Pętla live: szybki push stanu + odbiór komend od serwera.

    Interwał jest sterowany przez serwer — klient używa wartości z ostatniej odpowiedzi
    (zarówno 200 jak i 429). Startujemy z ``DEFAULT_LIVE_INTERVAL`` i nadpisujemy przy
    pierwszej odpowiedzi z poprawnym ``live_interval_seconds``.

    Obsługa różnych statusów (zwracanych przez ``async_send_live_data``):
        ``ok``           — wykonaj wszystkie komendy i prześpij ``interval`` sekund,
        ``disabled``     — admin wyłączył kanał, sprawdź ponownie za ``LIVE_DISABLED_RETRY`` s,
        ``rate_limited`` — śpij ``max(retry_after, interval)`` — synchronizacja z nowym rytmem,
        ``auth_error``   — długa przerwa (``LIVE_AUTH_RETRY``), żeby nie spamować przy złym kluczu,
        ``error``        — krótka przerwa równa ``interval``.
    """

    interval = coordinator_data.get("live_interval_seconds", DEFAULT_LIVE_INTERVAL)

    while True:
        try:
            status, server_interval, retry_after, pending_commands = await async_send_live_data(
                hass, coordinator_data
            )

            # Aktualizujemy lokalny interwał gdy serwer go dostarczył.
            # Dotyczy zarówno 200 jak i 429 — dzięki temu po rate limicie wychodzimy
            # od razu z poprawnym, dłuższym interwałem.
            if server_interval:
                interval = server_interval

            if status == "ok":
                # Komendy nie wykonujemy tu od razu — wrzucamy do kolejki write_managera.
                # Worker w tle przetworzy batch (execute → settling → verify → ACK),
                # a my możemy od razu wracać do kolejnego live pushu bez blokowania.
                if pending_commands and (write_manager := coordinator_data.get("write_manager")):
                    write_manager.enqueue(pending_commands)
                await asyncio.sleep(interval)

            elif status == "disabled":
                # Kanał wyłączony przez admina — nie ma sensu pushować częściej
                await asyncio.sleep(LIVE_DISABLED_RETRY)

            elif status == "rate_limited":
                # Czekamy minimum tyle co ``retry_after``, ale nie mniej niż interval,
                # żeby od razu wpaść w nowy rytm narzucony przez serwer
                wait = max(retry_after or 5, interval)
                _LOGGER.debug("Rate limit: śpię %ds (interval=%ds)", wait, interval)
                await asyncio.sleep(wait)

            elif status == "auth_error":
                # Zły klucz API — długa pauza, żeby nie hammerować serwera 401-kami
                await asyncio.sleep(LIVE_AUTH_RETRY)

            else:
                # Błąd sieciowy/serwerowy — normalna przerwa przed kolejną próbą
                await asyncio.sleep(interval)

        except asyncio.CancelledError:
            _LOGGER.debug("Pętla live anulowana")
            break
        except Exception as e:
            _LOGGER.exception("Nieoczekiwany błąd w pętli live: %s", e)
            await asyncio.sleep(interval)
