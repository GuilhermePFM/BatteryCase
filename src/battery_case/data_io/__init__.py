"""Input/output: where the inputs live, how they are read and described."""

from battery_case.data_io.loaders import load_battery_spec, load_market_prices
from battery_case.data_io.paths import (
    BATTERY_SPEC_XLSX,
    DATA_DIR,
    MARKET_PRICES_XLSX,
    PROJECT_ROOT,
    RAW_DATA_DIR,
    RESULTS_DIR,
)
from battery_case.data_io.quality import price_quality_report

__all__ = [
    "BATTERY_SPEC_XLSX",
    "DATA_DIR",
    "MARKET_PRICES_XLSX",
    "PROJECT_ROOT",
    "RAW_DATA_DIR",
    "RESULTS_DIR",
    "load_battery_spec",
    "load_market_prices",
    "price_quality_report",
]
