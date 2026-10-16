"""The common half-hourly grid: pairing, labelling, and windowing."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from battery_case.data_models import MarketPrices
from battery_case.modelling.grid import PERIODS_PER_HOUR, build_grid


def _prices(hours: int, *, market_1: list[float] | None = None) -> MarketPrices:
    hourly = pd.date_range("2024-01-01", periods=hours, freq="1h", name="timestamp")
    half_hourly = pd.date_range(
        "2024-01-01", periods=hours * PERIODS_PER_HOUR, freq="30min", name="timestamp"
    )
    values = market_1 if market_1 is not None else list(range(hours * PERIODS_PER_HOUR))
    return MarketPrices(
        market_1=pd.Series(values, index=half_hourly, dtype=float, name="market_1"),
        market_2=pd.Series(range(hours), index=hourly, dtype=float, name="market_2"),
    )


def test_hourly_prices_are_repeated_across_their_two_half_hours() -> None:
    grid = build_grid(_prices(3))

    assert len(grid) == 6
    assert grid.hours == 3
    np.testing.assert_array_equal(grid.price_2, [0, 0, 1, 1, 2, 2])
    np.testing.assert_array_equal(grid.price_1, [0, 1, 2, 3, 4, 5])


def test_grid_is_relabelled_from_market_2_so_mislabelled_rows_are_repaired() -> None:
    """The real Market 1 sheet mislabels an hour at each spring clock change."""
    prices = _prices(3)
    broken = prices.market_1.copy()
    broken.index = pd.DatetimeIndex(
        ["2024-01-01 00:00", "2024-01-01 00:30"] + ["2024-01-01 02:00", "2024-01-01 02:30"] * 2,
        name="timestamp",
    )
    grid = build_grid(MarketPrices(market_1=broken, market_2=prices.market_2))

    assert grid.timestamps.is_monotonic_increasing
    assert not grid.timestamps.duplicated().any()
    # The prices keep their order; only the labels come from Market 2.
    np.testing.assert_array_equal(grid.price_1, prices.market_1.to_numpy())


def test_mismatched_resolutions_are_rejected() -> None:
    prices = _prices(3)
    with pytest.raises(ValueError, match="expected 6"):
        build_grid(MarketPrices(market_1=prices.market_1.iloc[:-1], market_2=prices.market_2))


def test_window_truncates_at_the_end_of_the_grid() -> None:
    grid = build_grid(_prices(3))

    assert len(grid.window(2, 10)) == 4
    assert grid.window(2, 2).timestamps[0] == pd.Timestamp("2024-01-01 01:00")


def test_between_snaps_to_whole_hours() -> None:
    grid = build_grid(_prices(4))

    # An end landing on a half hour drops the part-hour rather than splitting it.
    window = grid.between("2024-01-01 01:00", "2024-01-01 02:00")
    assert len(window) % PERIODS_PER_HOUR == 0
    assert window.timestamps[0] == pd.Timestamp("2024-01-01 01:00")
    assert window.timestamps[-1] == pd.Timestamp("2024-01-01 01:30")

    assert len(grid.between()) == len(grid)
