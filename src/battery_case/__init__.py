"""Battery dispatch model for the Aurora second-round technical exercise.

The package is split three ways:

* :mod:`battery_case.data_models` — typed containers for the inputs;
* :mod:`battery_case.data_io` — paths, loaders and input data quality;
* :mod:`battery_case.modelling` — the dispatch model.
"""

from battery_case.data_io import load_battery_spec, load_market_prices, price_quality_report
from battery_case.data_models import BatterySpec, MarketPrices

__all__ = [
    "BatterySpec",
    "MarketPrices",
    "load_battery_spec",
    "load_market_prices",
    "price_quality_report",
]
