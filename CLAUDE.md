# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SolarAccelerator Home Assistant Integration - a custom integration that pushes solar inverter data from Home Assistant to the SolarAccelerator cloud service. Uses Push API model (no incoming connections needed).

## Architecture

```
custom_components/solaraccelerator/
├── __init__.py      # Entry setup, platform forwarding (sensor, button)
├── config_flow.py   # Multi-step config wizard: API validation → mode selection → entity mapping
├── const.py         # REQUIRED_ENTITIES (36 sensors), Solarman auto-mapping function
├── sensor.py        # 4 diagnostic sensors + hourly data push task (async_send_data_hourly)
├── button.py        # Force send button entity
├── strings.json     # UI strings (base)
└── translations/    # en.json, pl.json
```

**Data Flow:**
1. Config flow validates API key via GET `/api/homeassistant/test-connection`
2. User maps 36 HA entities to SolarAccelerator fields (or uses Solarman auto-mapping)
3. Background task at every full hour:
   - Sends JSON payload via POST `/api/homeassistant/send-data`
   - Polls GET `/api/homeassistant/data-ready` until server confirms processing
   - When ready=true, fetches updated prices and profit data
4. Force send button allows manual data push

**Key Constants:**
- `REQUIRED_ENTITIES` in const.py defines all 36 sensor mappings (PV, battery, inverter, grid, load, temp)
- `build_solarman_entity_mapping()` generates entity IDs from Solarman prefix
- API endpoints:
  - `API_TEST_CONNECTION_ENDPOINT = "/api/homeassistant/test-connection"`
  - `API_SEND_DATA_ENDPOINT = "/api/homeassistant/send-data"`
  - `API_DATA_READY_ENDPOINT = "/api/homeassistant/data-ready"`
  - `API_PRICES_ENDPOINT = "/api/homeassistant/prices"`
  - `API_PROFIT_ENDPOINT = "/api/homeassistant/profit"`

## Development Notes

- Requires Home Assistant 2024.1.0+
- Uses `aiohttp` for async HTTP requests
- Config flow has 6 entity mapping steps (one per category) for manual mode
- Data conversion in `convert_value()` handles HA state strings → API types

## Testing

No test framework configured. Manual testing requires a Home Assistant instance with the integration loaded.

## File Modification Patterns

When adding new entities:
1. Add to `REQUIRED_ENTITIES` in const.py (key, description, unit, category)
2. Add Solarman mapping in `build_solarman_entity_mapping()` if applicable
3. Update translations in strings.json and translations/*.json
