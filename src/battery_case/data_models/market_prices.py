"""Prices for the two wholesale markets of Attachment 2."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

MARKET_1_RESOLUTION = pd.Timedelta("30min")
MARKET_2_RESOLUTION = pd.Timedelta("1h")


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
