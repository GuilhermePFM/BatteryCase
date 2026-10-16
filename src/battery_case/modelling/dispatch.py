"""Where the dispatch model goes.

Deliberately left empty of methodology: the scaffolding below only fixes the
seam between "load the inputs" and "decide what the battery does", so the CLI,
the tests and the notebooks have something stable to import. Reshape it freely
once the approach is chosen.
"""

from __future__ import annotations

from typing import Protocol

import pandas as pd

from battery_case.data_models import BatterySpec, MarketPrices


class Dispatcher(Protocol):
    """Anything that turns prices into a schedule of battery actions."""

    def run(self, spec: BatterySpec, prices: MarketPrices) -> pd.DataFrame:
        """Return the dispatch schedule, indexed by settlement period."""
        ...
