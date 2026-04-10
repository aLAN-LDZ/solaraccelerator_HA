# SolarAccelerator Home Assistant Integration

Oficjalna integracja Home Assistant dla SolarAccelerator w trybie Push API.

Integracja pozwala wysyłać dane z inwertera (przez Home Assistant) do serwisu SolarAccelerator bez konieczności otwierania portów lub korzystania z Nabu Casa.

## Instalacja

### Via HACS (zalecane)

1. Dodaj to repozytorium jako custom repository w HACS
2. Wyszukaj "SolarAccelerator"
3. Kliknij Install
4. Uruchom ponownie Home Assistant

### Ręczna

1. Skopiuj folder `custom_components/solaraccelerator` do katalogu `custom_components` w Home Assistant
2. Uruchom ponownie Home Assistant

## Konfiguracja

### 1. Wygeneruj klucz API w SolarAccelerator

1. Zaloguj się do panelu SolarAccelerator
2. Przejdź do **Integracje → Inwertery**
3. W sekcji **Home Assistant** kliknij **Wygeneruj klucz API**
4. **Skopiuj i zapisz klucz** - nie będzie można go ponownie wyświetlić!

Klucz ma format: `sa_haapi_` + 32 znaki

### 2. Skonfiguruj integrację w Home Assistant

1. Przejdź do **Ustawienia → Urządzenia i usługi → Dodaj integrację**
2. Wyszukaj "SolarAccelerator"
3. Wprowadź:
   - **Klucz API**: Twój klucz wygenerowany w panelu SolarAccelerator
   - **Adres serwera**: `https://solaraccelerator.cloud` (domyślnie)

4. Po weryfikacji klucza API przejdziesz przez 6 kroków mapowania encji:
   - **PV**: 8 encji (moc, napięcie, prąd stringów PV, dzienna produkcja)
   - **Bateria**: 8 encji (moc, napięcie, prąd, SOC, SOH, temperatura)
   - **Inwerter**: 8 encji (status, napięcie/prąd L1-L3, moc)
   - **Sieć**: 7 encji (moc, CT L1-L3, import/eksport dzienny)
   - **Obciążenie**: 5 encji (zużycie dzienne, moc L1-L3, częstotliwość)
   - **Temperatury**: 2 encje (radiator, transformator DC)

5. Gotowe! Integracja zacznie wysyłać dane automatycznie o każdej pełnej godzinie.

## Obsługiwane encje (38 sensorów)

### PV (Panele fotowoltaiczne)
| Encja | Opis | Jednostka |
|-------|------|-----------|
| `day_pv_energy` | Dzienna produkcja PV | kWh |
| `pv1_power` | Moc PV string 1 | W |
| `pv2_power` | Moc PV string 2 | W |
| `pv1_voltage` | Napięcie PV string 1 | V |
| `pv2_voltage` | Napięcie PV string 2 | V |
| `pv1_current` | Prąd PV string 1 | A |
| `pv2_current` | Prąd PV string 2 | A |
| `total_pv_generation` | Całkowita generacja PV | kWh |

### Bateria
| Encja | Opis | Jednostka |
|-------|------|-----------|
| `day_battery_discharge` | Dzienne rozładowanie baterii | kWh |
| `day_battery_charge` | Dzienne ładowanie baterii | kWh |
| `battery_power` | Moc baterii (+ ładowanie, - rozładowanie) | W |
| `battery_current` | Prąd baterii | A |
| `battery_temp` | Temperatura baterii | °C |
| `battery_voltage` | Napięcie baterii | V |
| `battery_soc` | Stan naładowania baterii | % |
| `battery_soh` | Stan zdrowia baterii | % |

### Inwerter
| Encja | Opis | Jednostka |
|-------|------|-----------|
| `inverter_status` | Status inwertera | - |
| `inverter_voltage_l1` | Napięcie L1 | V |
| `inverter_voltage_l2` | Napięcie L2 | V |
| `inverter_voltage_l3` | Napięcie L3 | V |
| `inverter_current_l1` | Prąd L1 | A |
| `inverter_current_l2` | Prąd L2 | A |
| `inverter_current_l3` | Prąd L3 | A |
| `inverter_power` | Moc inwertera | W |

### Sieć
| Encja | Opis | Jednostka |
|-------|------|-----------|
| `grid_power` | Moc sieci (+ pobór, - oddawanie) | W |
| `grid_ct_power_l1` | Moc CT L1 | W |
| `grid_ct_power_l2` | Moc CT L2 | W |
| `grid_ct_power_l3` | Moc CT L3 | W |
| `day_grid_import` | Dzienny pobór z sieci | kWh |
| `day_grid_export` | Dzienne oddanie do sieci | kWh |
| `grid_connected_status` | Status połączenia z siecią | bool |

### Obciążenie
| Encja | Opis | Jednostka |
|-------|------|-----------|
| `day_load_energy` | Dzienne zużycie | kWh |
| `load_power_l1` | Moc obciążenia L1 | W |
| `load_power_l2` | Moc obciążenia L2 | W |
| `load_power_l3` | Moc obciążenia L3 | W |
| `load_frequency` | Częstotliwość sieci | Hz |

### Temperatury
| Encja | Opis | Jednostka |
|-------|------|-----------|
| `radiator_temp` | Temperatura radiatora | °C |
| `dc_transformer_temp` | Temperatura transformatora DC | °C |

## Encje diagnostyczne

Integracja tworzy urządzenie "SolarAccelerator" z następującymi sensorami:

- **Status połączenia**: Aktualny stan połączenia z serwerem
  - `connected` - połączono pomyślnie
  - `disconnected` - brak połączenia
  - `auth_error` - błąd autoryzacji (nieprawidłowy klucz API)
  - `error` - inny błąd

- **Ostatnie wysłanie**: Timestamp ostatniego pomyślnego wysłania danych

- **Wysłane encje**: Liczba encji wysłanych w ostatnim żądaniu

## Jak to działa

1. Integracja waliduje klucz API poprzez testowe żądanie do API
2. Po skonfigurowaniu mapowania encji, integracja cyklicznie:
   - Pobiera aktualny stan wszystkich zmapowanych encji z HA
   - Konwertuje wartości do odpowiednich typów (float, int, bool)
   - Wysyła dane do API SolarAccelerator w formacie JSON
3. Status połączenia jest aktualizowany na podstawie odpowiedzi serwera

## Format API

### Test połączenia
```
GET https://solaraccelerator.cloud/api/homeassistant/test-connection
Authorization: Bearer sa_haapi_...
```

### Wysyłanie danych
```
POST https://solaraccelerator.cloud/api/homeassistant/send-data
Authorization: Bearer sa_haapi_...
Content-Type: application/json

{
  "timestamp": "2024-01-18T12:00:00.000Z",
  "entities": {
    "pv1_power": 1500,
    "pv2_power": 1200,
    "battery_soc": 85,
    "battery_power": 500,
    "grid_power": -200,
    ...
  }
}
```

## Rozwiązywanie problemów

### Błąd "Nieprawidłowy klucz API"
- Upewnij się, że klucz zaczyna się od `sa_haapi_`
- Sprawdź czy klucz został skopiowany w całości (min. 40 znaków)
- Wygeneruj nowy klucz w panelu SolarAccelerator

### Błąd "Nie można połączyć się z serwerem"
- Sprawdź połączenie internetowe Home Assistant
- Zweryfikuj czy adres serwera jest poprawny
- Sprawdź czy serwer SolarAccelerator jest dostępny

### Status "disconnected"
- Sprawdź logi Home Assistant w **Ustawienia → System → Logi**
- Poszukaj wpisów z `solaraccelerator`

## Licencja

MIT
