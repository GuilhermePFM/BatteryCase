"""The common half-hourly grid the model is posed on (§1, §5 "Data handling").

Market 1 settles half-hourly and Market 2 hourly, so both are projected onto one
half-hourly grid: period ``i`` belongs to hour ``i // 2``, and Market 2's hourly
price is repeated across the two half hours it covers.

The pairing is **positional**, not by timestamp. Every day of the horizon holds
exactly 48 Market 1 rows and 24 Market 2 rows, so position carries the period
ordering reliably, whereas the Market 1 labels do not: at each spring clock
change that sheet labels the 01:00-02:00 hour as 02:00, which is why its index
is not monotonic there. Market 2's labels are taken as canonical and the grid is
relabelled from them, which repairs the artefact without moving any price off
the settlement period it was quoted for.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from battery_case.data_models import MARKET_2_RESOLUTION, MarketPrices

#: Length of a settlement period on the common grid, in hours (§2, ``dt``).
PERIOD_HOURS = 0.5

#: Half-hourly periods per hourly Market 2 interval.
PERIODS_PER_HOUR = 2


@dataclass(frozen=True, slots=True)
class DispatchGrid:
    """Prices for both markets on the common half-hourly grid.

    ``price_2`` is the hourly price repeated across each hour's two half hours;
    the hourly commitment of §4.5 is imposed on the decision variables, not by
    the prices.
    """

    timestamps: pd.DatetimeIndex
    price_1: np.ndarray
    price_2: np.ndarray

    def __post_init__(self) -> None:
        if not (len(self.timestamps) == len(self.price_1) == len(self.price_2)):
            raise ValueError("Grid timestamps and price arrays must be the same length")
        if len(self) % PERIODS_PER_HOUR:
            raise ValueError(f"Grid must hold whole hours, got {len(self)} periods")

    def __len__(self) -> int:
        return len(self.timestamps)

    @property
    def hours(self) -> int:
        """Number of whole Market 2 intervals on the grid."""
        return len(self) // PERIODS_PER_HOUR

    def window(self, start: int, periods: int) -> DispatchGrid:
        """Return the sub-grid of ``periods`` periods starting at index ``start``."""
        stop = min(start + periods, len(self))
        return DispatchGrid(
            timestamps=self.timestamps[start:stop],
            price_1=self.price_1[start:stop],
            price_2=self.price_2[start:stop],
        )

    def between(
        self,
        start: str | pd.Timestamp | None = None,
        end: str | pd.Timestamp | None = None,
    ) -> DispatchGrid:
        """Return the sub-grid covering ``[start, end]``, inclusive.

        The window is aligned to whole hours so that no Market 2 interval is cut
        in half and the commitment of §4.5 stays well defined: the start moves
        back to its hour boundary, and a trailing part-hour is dropped.
        """
        low = 0 if start is None else int(self.timestamps.searchsorted(pd.Timestamp(start)))
        high = (
            len(self)
            if end is None
            else int(self.timestamps.searchsorted(pd.Timestamp(end), side="right"))
        )
        low -= low % PERIODS_PER_HOUR
        return self.window(low, _whole_hours(high - low))


def _whole_hours(periods: int) -> int:
    return periods - periods % PERIODS_PER_HOUR


def build_grid(prices: MarketPrices) -> DispatchGrid:
    """Project both markets onto the common half-hourly grid."""
    market_1, market_2 = prices.market_1, prices.market_2

    expected = len(market_2) * PERIODS_PER_HOUR
    if len(market_1) != expected:
        raise ValueError(
            f"Market 1 has {len(market_1)} periods; expected {expected}, "
            f"two per Market 2 hour ({len(market_2)} hours)"
        )

    offsets = pd.to_timedelta(np.arange(PERIODS_PER_HOUR) * MARKET_2_RESOLUTION / PERIODS_PER_HOUR)
    timestamps = pd.DatetimeIndex(
        (market_2.index.values[:, None] + offsets.values[None, :]).ravel(),
        name="timestamp",
    )

    return DispatchGrid(
        timestamps=timestamps,
        price_1=market_1.to_numpy(dtype=float),
        price_2=np.repeat(market_2.to_numpy(dtype=float), PERIODS_PER_HOUR),
    )
