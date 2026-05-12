"""Klasy encji sensorów Solar Accelerator pogrupowane tematycznie.

Każdy submoduł odpowiada za jedną kategorię:
- ``diagnostic`` — stan połączenia, znaczniki czasu, licznik encji,
- ``prices``     — ceny zakupu/sprzedaży energii + flagi tania/droga,
- ``profit``     — dzienny zysk i wartość energii w baterii,
- ``live``       — stan kanału live (status, ostatni push, interwał).

``__init__.py`` służy wyłącznie jako re-eksport, żeby ``sensor.py`` mógł
importować wszystkie klasy z jednego miejsca.
"""
from .diagnostic import (
    SolarAcceleratorEntitiesCountSensor,
    SolarAcceleratorLastSentSensor,
    SolarAcceleratorNextScheduledSensor,
    SolarAcceleratorStatusSensor,
)
from .live import (
    SolarAcceleratorLiveIntervalSensor,
    SolarAcceleratorLiveLastPushSensor,
    SolarAcceleratorLiveStatusSensor,
)
from .prices import (
    SolarAcceleratorAverageBuyPriceSensor,
    SolarAcceleratorAverageSellPriceSensor,
    SolarAcceleratorCurrentBuyPriceSensor,
    SolarAcceleratorCurrentSellPriceSensor,
    SolarAcceleratorIsCheapSensor,
    SolarAcceleratorIsExpensiveSensor,
    SolarAcceleratorMaxBuyPriceSensor,
    SolarAcceleratorMaxSellPriceSensor,
    SolarAcceleratorMinBuyPriceSensor,
    SolarAcceleratorMinSellPriceSensor,
    SolarAcceleratorPriceProviderSensor,
)
from .profit import (
    SolarAcceleratorBatteryAvgPriceSensor,
    SolarAcceleratorBatteryValueSensor,
    SolarAcceleratorDailyProfitSensor,
)

__all__ = [
    # diagnostyczne
    "SolarAcceleratorStatusSensor",
    "SolarAcceleratorLastSentSensor",
    "SolarAcceleratorNextScheduledSensor",
    "SolarAcceleratorEntitiesCountSensor",
    # ceny
    "SolarAcceleratorCurrentBuyPriceSensor",
    "SolarAcceleratorMinBuyPriceSensor",
    "SolarAcceleratorMaxBuyPriceSensor",
    "SolarAcceleratorAverageBuyPriceSensor",
    "SolarAcceleratorCurrentSellPriceSensor",
    "SolarAcceleratorMinSellPriceSensor",
    "SolarAcceleratorMaxSellPriceSensor",
    "SolarAcceleratorAverageSellPriceSensor",
    "SolarAcceleratorIsCheapSensor",
    "SolarAcceleratorIsExpensiveSensor",
    "SolarAcceleratorPriceProviderSensor",
    # zysk i bateria
    "SolarAcceleratorDailyProfitSensor",
    "SolarAcceleratorBatteryValueSensor",
    "SolarAcceleratorBatteryAvgPriceSensor",
    # kanał live
    "SolarAcceleratorLiveStatusSensor",
    "SolarAcceleratorLiveLastPushSensor",
    "SolarAcceleratorLiveIntervalSensor",
]
