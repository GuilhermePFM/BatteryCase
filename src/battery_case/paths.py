"""Canonical locations of the inputs and outputs shipped with the repository."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
RESULTS_DIR = DATA_DIR / "results"

BATTERY_SPEC_XLSX = RAW_DATA_DIR / "attachment_1_battery_spec.xlsx"
MARKET_PRICES_XLSX = RAW_DATA_DIR / "attachment_2_market_prices.xlsx"
