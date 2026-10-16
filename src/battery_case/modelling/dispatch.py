"""The seam between loading the inputs and deciding what the battery does.

Anything implementing :class:`Dispatcher` can be run against the data and have
its schedule scored the same way, which keeps the CLI, the tests and the
notebooks independent of how the decision is reached.
:class:`~battery_case.modelling.rolling.RollingDispatcher` is the implementation
of the formulation in ``docs/model/model.md``; a heuristic benchmark would
implement the same protocol.
"""

from __future__ import annotations

from typing import Protocol

import pandas as pd

from battery_case.data_models import BatterySpec, MarketPrices


class Dispatcher(Protocol):
    """Anything that turns prices into a schedule of battery actions."""

    def run(self, spec: BatterySpec, prices: MarketPrices) -> pd.DataFrame:
        """Return the dispatch schedule, indexed by settlement period.

        The columns are those of
        :data:`battery_case.modelling.schedule.COLUMNS`, so that
        :func:`~battery_case.modelling.schedule.summarise` can score any
        dispatcher's output.
        """
        ...
