"""Wykonywanie komend HA przekazanych z backendu Solar Accelerator.

Serwer wysyła komendy w odpowiedzi na live push (pole ``pending_commands``).
Każda komenda opisuje wywołanie usługi HA — domain, service, entity_id i opcjonalne
``service_data``. Tu są one wykonywane przez ``hass.services.async_call``.

UWAGA: aktualnie integracja ufa komendom z serwera bez walidacji allowlisty
(to jest zaplanowany Etap 4 refaktoru — warstwa security).
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


async def async_execute_command(
    hass: HomeAssistant,
    cmd: dict[str, Any],
) -> tuple[bool, str | None]:
    """Wykonaj pojedynczą komendę HA otrzymaną z backendu.

    Format komendy z serwera:
        {"id": "...", "domain": "switch", "service": "turn_on",
         "entity_id": "switch.foo", "service_data": {...}}

    Zwraca krotkę ``(success, error_message)``:
    - ``success=True``, ``error=None`` — gdy ``async_call`` zakończył się bez wyjątku,
    - ``success=False``, ``error="..."`` — gdy brakuje pól lub wywołanie rzuciło wyjątek.

    Komunikat błędu jest przycinany do 500 znaków, żeby zmieścił się w odpowiedzi ACK
    wysyłanej z powrotem do serwera.
    """
    domain = cmd.get("domain")
    service = cmd.get("service")
    entity_id = cmd.get("entity_id")
    service_data = cmd.get("service_data") or {}

    if not domain or not service or not entity_id:
        return (False, "Invalid command: missing domain/service/entity_id")

    try:
        await hass.services.async_call(
            domain,
            service,
            {"entity_id": entity_id, **service_data},
            blocking=True,
        )
        _LOGGER.info("Wykonano komendę: %s.%s na %s", domain, service, entity_id)
        return (True, None)
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        _LOGGER.error(
            "Komenda nieudana (%s.%s na %s): %s",
            domain, service, entity_id, error_msg,
        )
        return (False, error_msg[:500])
