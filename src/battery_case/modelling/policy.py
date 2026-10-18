"""The seam between loading the inputs and deciding what the battery does.

Anything implementing :class:`DispatchPolicy` can be run against the data and have
its plan scored the same way, which keeps the CLI, the tests and the
notebooks independent of how the decision is reached.
:class:`~battery_case.modelling.rolling_horizon.RollingPolicy` is the implementation
of the formulation in ``docs/model/model.md``; a heuristic benchmark would
implement the same protocol.
"""

from __future__ import annotations

from typing import Protocol

import pandas as pd

from battery_case.data_models import BatterySpec, MarketPrices


class DispatchPolicy(Protocol):
    """Anything that turns prices into a plan of battery actions."""

    def run(self, spec: BatterySpec, prices: MarketPrices) -> pd.DataFrame:
        """Return the dispatch plan, indexed by settlement period.

        The columns are those of
        :data:`battery_case.modelling.plan.COLUMNS`, so that
        :func:`~battery_case.modelling.plan.summarise` can score any
        policy's output.
        """
        ...
