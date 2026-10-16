"""Data models: the typed description of the exercise inputs.

Plain containers only — no loading, no modelling.
"""

from battery_case.data_models.battery import BatterySpec
from battery_case.data_models.market_prices import (
    MARKET_1_RESOLUTION,
    MARKET_2_RESOLUTION,
    MarketPrices,
)

__all__ = [
    "MARKET_1_RESOLUTION",
    "MARKET_2_RESOLUTION",
    "BatterySpec",
    "MarketPrices",
]
