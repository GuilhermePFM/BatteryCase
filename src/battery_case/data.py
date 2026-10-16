"""Loading of the two spreadsheets supplied with the exercise.

The loaders stay deliberately thin: they read, name and *describe* the inputs,
and leave every modelling choice to :mod:`battery_case.dispatch`. In particular
the known timestamp anomalies around the clock changes (see
:func:`price_quality_report`) are reported, not silently repaired.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from battery_case.battery import BatterySpec
from battery_case.paths import BATTERY_SPEC_XLSX, MARKET_PRICES_XLSX

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

MARKET_1_RESOLUTION = pd.Timedelta("30min")
MARKET_2_RESOLUTION = pd.Timedelta("1h")


def load_battery_spec(path: Path | str = BATTERY_SPEC_XLSX) -> BatterySpec:
    """Read Attachment 1 into a :class:`BatterySpec`."""
    frame = pd.read_excel(path, sheet_name="Data", index_col=0)
    values = frame["Values"]

    missing = [label for label in _SPEC_FIELDS if label not in values.index]
    if missing:
        raise ValueError(f"Battery spec is missing expected rows: {missing}")

    return BatterySpec(**{field: float(values[label]) for label, field in _SPEC_FIELDS.items()})


@dataclass(frozen=True, slots=True)
class MarketPrices:
    """Prices for both wholesale markets, each at its own native resolution.

    ``market_1`` is half-hourly and ``market_2`` hourly; both are £/MWh indexed
    by the timestamp at which the settlement period *starts*, in the order the
    spreadsheet lists them.
    """

    market_1: pd.Series
    market_2: pd.Series

    @property
    def start(self) -> pd.Timestamp:
        return pd.Timestamp(min(self.market_1.index.min(), self.market_2.index.min()))

    @property
    def end(self) -> pd.Timestamp:
        return pd.Timestamp(max(self.market_1.index.max(), self.market_2.index.max()))

    def between(self, start: str | pd.Timestamp, end: str | pd.Timestamp) -> MarketPrices:
        """Return the same prices restricted to ``[start, end]`` inclusive.

        Uses a mask rather than ``.loc`` slicing because the raw index is not
        monotonic at the spring clock changes.
        """
        lo, hi = pd.Timestamp(start), pd.Timestamp(end)
        return MarketPrices(
            market_1=self.market_1[(self.market_1.index >= lo) & (self.market_1.index <= hi)],
            market_2=self.market_2[(self.market_2.index >= lo) & (self.market_2.index <= hi)],
        )


def load_market_prices(path: Path | str = MARKET_PRICES_XLSX) -> MarketPrices:
    """Read Attachment 2 into a :class:`MarketPrices`.

    The hourly sheet is laid out on the half-hourly grid with blank rows on the
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


def price_quality_report(prices: MarketPrices) -> pd.DataFrame:
    """Summarise the timestamp anomalies in each market.

    Both markets carry artefacts of UK daylight saving: Market 1 repeats two
    half hours at every spring clock change (and the index therefore steps
    backwards there), while neither market repeats the extra autumn hour. How
    to treat these periods is a modelling decision.
    """
    rows = [
        _quality_row("market_1", prices.market_1, MARKET_1_RESOLUTION),
        _quality_row("market_2", prices.market_2, MARKET_2_RESOLUTION),
    ]
    return pd.DataFrame(rows).set_index("market")


def _quality_row(name: str, series: pd.Series, resolution: pd.Timedelta) -> dict[str, object]:
    steps = series.index.to_series().diff().dropna()
    return {
        "market": name,
        "periods": len(series),
        "first": series.index.min(),
        "last": series.index.max(),
        "resolution": resolution,
        "duplicate_timestamps": int(series.index.duplicated().sum()),
        "irregular_steps": int((steps != resolution).sum()),
        "monotonic": bool(series.index.is_monotonic_increasing),
        "missing_prices": int(series.isna().sum()),
    }
