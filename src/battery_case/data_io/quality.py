"""Description of the input data: what the spreadsheets actually contain.

Reporting only — the anomalies are surfaced here and dealt with (or not) by
:mod:`battery_case.modelling`.
"""

from __future__ import annotations

import pandas as pd

from battery_case.data_models import MARKET_1_RESOLUTION, MARKET_2_RESOLUTION, MarketPrices


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
