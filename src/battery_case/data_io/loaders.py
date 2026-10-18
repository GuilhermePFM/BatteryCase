"""Loading of the two spreadsheets supplied with the exercise.

The loaders stay deliberately thin: they read and name the inputs, and leave
every modelling choice to :mod:`battery_case.modelling`. The known timestamp
anomalies around the clock changes are reported by
:mod:`battery_case.data_io.quality`, not silently repaired.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from battery_case.data_io.paths import BATTERY_SPEC_XLSX, MARKET_PRICES_XLSX
from battery_case.data_models import BatterySpec, MarketPrices

#: Row labels in Attachment 1 mapped onto :class:`BatterySpec` fields.
_SPEC_FIELDS: dict[str, str] = {
    "Max charging rate": "max_charge_rate_mw",
    "Max discharging rate": "max_discharge_rate_mw",
    "Max storage volume": "max_storage_volume_mwh",
    "Battery charging efficiency": "charging_loss_fraction",
    "Battery discharging efficiency": "discharging_loss_fraction",
    "Lifetime (1)": "lifetime_years",
    "Lifetime (2)": "lifetime_cycles",
    "Storage volume degradation rate": "degradation_pct_per_cycle",
    "Capex": "capex_gbp",
    "Fixed Operational Costs": "fixed_opex_gbp_per_year",
}

MARKET_1_SHEET = "Half-hourly data"
MARKET_2_SHEET = "Hourly data"


def load_battery_spec(path: Path | str = BATTERY_SPEC_XLSX) -> BatterySpec:
    """Read Attachment 1 into a :class:`BatterySpec`."""
    frame = pd.read_excel(path, sheet_name="Data", index_col=0)
    values = frame["Values"]

    missing = [label for label in _SPEC_FIELDS if label not in values.index]
    if missing:
        raise ValueError(f"Battery spec is missing expected rows: {missing}")

    return BatterySpec(**{field: float(values[label]) for label, field in _SPEC_FIELDS.items()})


def load_market_prices(path: Path | str = MARKET_PRICES_XLSX) -> MarketPrices:
    """Read Attachment 2 into a :class:`MarketPrices`.

    The hourly sheet is laid out on the half-hourly settlement with blank rows on the
    half hours; those are dropped so each series keeps its own resolution.
    """
    sheets = pd.read_excel(path, sheet_name=[MARKET_1_SHEET, MARKET_2_SHEET], index_col=0)
    return MarketPrices(
        market_1=_read_price_series(sheets[MARKET_1_SHEET], "market_1"),
        market_2=_read_price_series(sheets[MARKET_2_SHEET], "market_2"),
    )


def _read_price_series(frame: pd.DataFrame, name: str) -> pd.Series:
    """Take the single price column of a sheet and drop the blank rows.

    Timestamps are rounded to the minute: Excel stores them as floats, so some
    land on ``00:59:59.999``. Row order is preserved — it is the order in which
    the settlement periods occur.
    """
    if frame.shape[1] != 1:
        raise ValueError(f"Expected one price column for {name}, got {list(frame.columns)}")

    series = frame.iloc[:, 0].dropna().astype(float).rename(name)
    series.index = pd.to_datetime(series.index).round("min")
    series.index.name = "timestamp"
    return series
