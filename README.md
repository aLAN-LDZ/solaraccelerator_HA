# SolarAccelerator Home Assistant Integration

Oficjalna integracja Home Assistant dla SolarAccelerator działająca w trybie Push API.

Integracja:
- **wysyła** dane z falownika (i opcjonalnie ładowarki EV) do serwisu SolarAccelerator — bez otwierania portów ani Nabu Casa,
- utrzymuje **kanał live** (szybki push stanu co kilkanaście sekund),
- **odbiera komendy** z serwisu i zapisuje ustawienia falownika (np. tryb pracy, limity prądu, harmonogram), z weryfikacją i ponawianiem,
- **pilnuje ustawień** — przywraca wartości z planu, gdy falownik sam wróci do poprzednich.

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
4. **Skopiuj i zapisz klucz** — nie będzie można go ponownie wyświetlić!

Klucz ma format: `sa_haapi_` + 32 znaki.

### 2. Dodaj integrację w Home Assistant

1. Przejdź do **Ustawienia → Urządzenia i usługi → Dodaj integrację**
2. Wyszukaj "SolarAccelerator"
3. Podaj **Klucz API** oraz **Adres serwera** (domyślnie `https://solaraccelerator.cloud`)

Po weryfikacji klucza kreator przeprowadzi przez kolejne kroki:

**Falownik**
1. **Model i tryb konfiguracji** — wybierasz model falownika (np. *Deye — SG0\*LP3*) oraz sposób mapowania encji:
   - **Solarman — prefix (zalecane)** — integracja sama zbuduje mapowanie wg konwencji nazw integracji *Solarman* (HACS). Podajesz tylko prefix encji (np. `deye` dla `sensor.deye_pv1_power`).
   - **SolarAssistant — prefix** — automatyczne mapowanie dla appliance *SolarAssistant* (MQTT). Podajesz prefix urządzenia falownika (np. `deye_sunsynk_sol_ark_3_phase` dla `sensor.deye_sunsynk_sol_ark_3_phase_pv_power`). Ten sam falownik, inne nazwy encji — integracja wybierze właściwy schemat zarówno dla odczytu danych, jak i dla sterowania z optymalizatora.
   - **Ręczny** — wybierasz każdą encję z Home Assistant samodzielnie (kroki: PV → Bateria → Inwerter → Sieć → Obciążenie → Temperatury).

   > **SolarAssistant — uwagi:** liczniki energii (`*_energy_*`) są dzienne (resetują się dobowo) — dokładnie tego oczekuje serwis. Kilku sensorów diagnostycznych SolarAssistant nie wystawia (całkowita produkcja PV, SOH baterii, prąd/moc falownika per faza, status on/off‑grid, osobna temperatura transformatora DC) — pozostają puste i nie wpływają na obliczenia. Curtailment PV przy wymuszonym ładowaniu z sieci (`max_solar_power`) jest pominięty, bo ta encja siedzi pod drugim urządzeniem SolarAssistant.

**Ładowarka EV (opcjonalnie)**
2. **Czy masz ładowarkę EV przez OCPP?** — jeśli tak, analogicznie wybierasz model (np. *Autel — MaxiChargerAC 7.5KW*) i tryb (prefix integracji *OCPP* albo ręczne mapowanie).

Gotowe — integracja zacznie wysyłać dane automatycznie o każdej pełnej godzinie oraz utrzymywać kanał live.

## Dane wysyłane z falownika

Te encje pobierasz/mapujesz w Home Assistant; integracja odczytuje ich stan i wysyła do serwisu.

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
| `battery_power` | Moc baterii (+ ładowanie, − rozładowanie) | W |
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
| `grid_power` | Moc sieci (+ pobór, − oddawanie) | W |
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

### Ładowarka EV (OCPP) — opcjonalnie
Wysyłane tylko gdy włączysz ładowarkę EV i podasz prefix.

| Encja | Opis | Jednostka |
|-------|------|-----------|
| `status` | Status ładowarki | - |
| `status_connector` | Status połączenia | - |
| `vendor` | Producent ładowarki | - |
| `power_active_import` | Moc ładowania | kW |
| `energy_session` | Energia sesji | kWh |
| `energy_active_import_register` | Licznik energii | kWh |
| `current_import` | Prąd ładowania | A |
| `voltage` | Napięcie | V |
| `time_session` | Czas sesji | min |
| `error_code` | Kod błędu | - |
| `transaction_id` | ID transakcji | - |

## Sterowalne odbiorniki (Konfiguruj)

Poza falownikiem i ładowarką możesz udostępnić serwisowi dodatkowe **sterowalne
odbiorniki** (CWU/bojler, pompa ciepła, druga ładowarka itp.), które
optymalizator będzie mógł uruchamiać w najtańszych godzinach lub przy nadwyżce
produkcji.

Na karcie integracji w Home Assistant kliknij **Konfiguruj** — otworzy się menu:

- **Dodaj urządzenie** — podajesz nazwę, typ (EV / CWU / pompa / inne), encję
  włącznika (`switch`/`input_boolean`) oraz opcjonalnie encje mocy, energii i
  statusu i moc znamionową.
- **Usuń urządzenie** — zaznaczasz urządzenia do skasowania.
- **Zapisz i zakończ** — lista trafia do serwisu (pojawi się w
  `Konfiguracja PV → Sterowalne odbiorniki`), a integracja przeładuje się
  automatycznie.

Definicje i bieżący stan tych encji są dosyłane w każdej paczce danych. Sam
sposób ładowania (np. tryby EV: „teraz" / „do rana" / „najlepsze okno")
ustawiasz po stronie serwisu.

## Sterowanie falownikiem

Integracja może odbierać komendy z serwisu SolarAccelerator i zapisywać ustawienia falownika (np. tryb pracy, limity prądu ładowania/rozładowania, harmonogram). Komendy są wykonywane przez wewnętrzny **WriteManager**, który:

1. wykonuje komendy **sekwencyjnie**, z konfigurowalnym odstępem między nimi,
2. po zapisie czeka aż falownik się **ustabilizuje**, po czym **weryfikuje**, że wartość faktycznie się zmieniła,
3. **ponawia** zapis, jeśli weryfikacja się nie powiodła (np. Modbus odrzucił pakiet).

Powód: falownik (Modbus przez Solarman) nie nadąża, gdy uderza w niego kilka zapisów naraz — część komend bywa po cichu odrzucana. Kolejka z opóźnieniami i weryfikacją sprawia, że zapisy są niezawodne.

### Encje konfiguracyjne (kategoria: Konfiguracja)

Pozwalają stroić zachowanie WriteManagera z poziomu UI, bez restartu integracji:

| Encja | Opis | Domyślnie |
|-------|------|-----------|
| **Opóźnienie między komendami** | Sekund między kolejnymi zapisami w jednej paczce | 1.5 s |
| **Opóźnienie przed verify** | Sekund od ostatniego zapisu do odczytu weryfikacyjnego | 5.0 s |
| **Liczba prób verify** | Ile razy ponowić zapis, gdy weryfikacja zawiedzie | 3 |

## Pilnuj ustawień

Przełącznik **„Pilnuj ustawień"** (domyślnie **włączony**) rozwiązuje znany problem falowników Deye/Solarman: po udanym zapisie rejestr potrafi po kilku–kilkunastu minutach **sam wrócić** do poprzedniej wartości — przez co plan przestaje być realizowany, mimo że komenda raz się wykonała.

Gdy funkcja jest włączona, integracja po każdej komendzie zapamiętuje docelowy stan sterowanych encji i pilnuje go przez całą godzinę:

- **reaguje natychmiast** na zmianę stanu encji,
- dodatkowo **co 60 s sprawdza** wszystkie pilnowane encje — łapie też przypadki, gdy falownik utknął na złej wartości bez zgłoszenia zmiany lub gdy poprzednia korekta nie zadziałała,
- przy wykryciu odchylenia **przywraca** wartość z planu.

Pilnowanie trwa do końca bieżącej godziny (lub do nadejścia nowego planu). Wyłączenie przełącznika zatrzymuje przywracanie — integracja dalej wysyła i odbiera dane, ale nie ingeruje w ręczne zmiany ustawień falownika.

## Encje tworzone przez integrację

Integracja tworzy urządzenie **„Solar Accelerator"** z następującymi encjami.

### Diagnostyka
- **Status połączenia** — `connected` / `disconnected` / `auth_error` / `error`
- **Ostatnie wysłanie** — czas ostatniej udanej wysyłki paczki godzinowej
- **Następne wysłanie** — zaplanowany czas kolejnej wysyłki
- **Wysłane encje** — liczba encji z odczytanym stanem w ostatniej paczce
- **Diagnostyka komend** — statystyki zapisów do falownika (status, liczba ponowień per encja)

### Kanał live
- **Status LIVE** — `live` / `inactive` / `disabled` / `rate_limited` / `auth_error` / `error`
- **Ostatni push LIVE** — czas ostatniego pushu live
- **Interwał LIVE** — aktualny odstęp między pushami live

### Ceny energii
- **Cena zakupu energii** oraz **min / max / średnia** na dziś
- **Cena sprzedaży energii** oraz **min / max / średnia** na dziś
- **Tania energia** / **Droga energia** — flagi bieżącej godziny
- **Dostawca cen**

### Zysk
- **Dzienny zysk**
- **Wartość baterii**
- **Średnia cena baterii**

### Sterowanie
- **Synchronizuj** (przycisk) — wymusza natychmiastową wysyłkę danych poza harmonogramem (przydatne po zmianie mapowania)
- **Opóźnienie między komendami**, **Opóźnienie przed verify**, **Liczba prób verify** (number) — patrz *Sterowanie falownikiem*
- **Pilnuj ustawień** (przełącznik) — patrz *Pilnuj ustawień*

## Jak to działa

1. Integracja waliduje klucz API przy konfiguracji.
2. Co pełną godzinę wysyła pełną paczkę zmapowanych encji oraz pobiera aktualne ceny i (po przetworzeniu) dzienny zysk.
3. Między godzinami utrzymuje kanał live — szybki push stanu; jego interwał jest sterowany zdalnie.
4. W odpowiedzi na kanale live może otrzymać komendy do falownika — wykonuje je przez WriteManager (zapis → stabilizacja → weryfikacja → ewentualne ponowienie).
5. Jeśli „Pilnuj ustawień" jest włączone, przez całą godzinę pilnuje, by zapisane wartości się utrzymały.

## Rozwiązywanie problemów

### Błąd „Nieprawidłowy klucz API"
- Upewnij się, że klucz zaczyna się od `sa_haapi_`
- Sprawdź, czy klucz został skopiowany w całości (min. 40 znaków)
- W razie potrzeby wygeneruj nowy klucz w panelu SolarAccelerator

### Błąd „Nie można połączyć się z serwerem"
- Sprawdź połączenie internetowe Home Assistant
- Zweryfikuj poprawność adresu serwera

### Status „disconnected" / „error"
- Sprawdź logi w **Ustawienia → System → Logi** i poszukaj wpisów z `solaraccelerator`

### Status LIVE „disabled"
- Kanał live został wyłączony po stronie serwisu — integracja sprawdzi ponownie automatycznie

### Komendy do falownika nie „trzymają się"
- Włącz przełącznik **Pilnuj ustawień**
- Sprawdź encję **Diagnostyka komend** — pokazuje status i liczbę ponowień per encja
- Jeśli zapisy są odrzucane, zwiększ **Opóźnienie między komendami** / **Opóźnienie przed verify** lub **Liczbę prób verify**

## Licencja

MIT
