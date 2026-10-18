"""The way a calibrated run reaches the CLI (§6).

:class:`CalibratedPolicy` adapts a search to the ``DispatchPolicy`` protocol, so
that a calibrated run is still "prices in, plan out" as far as
:func:`~battery_case.modelling.plan.summarise`, the CLI and the notebooks
are concerned. Which method it runs comes from
:mod:`~battery_case.modelling.cycle_value.searches`; what the method does with the
horizon is :mod:`~battery_case.modelling.cycle_value.oracle`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from battery_case.data_models import BatterySpec, MarketPrices
from battery_case.modelling.cycle_value.oracle import CycleOracle, DualSearch, DualSearchResult
from battery_case.modelling.cycle_value.searches import DEFAULT_SEARCH, SEARCHES
from battery_case.modelling.parameters import ModelParameters
from battery_case.modelling.periods import SettlementPeriods, build_periods
from battery_case.modelling.rolling_horizon import RollingPolicy


@dataclass(frozen=True, slots=True)
class CalibratedPolicy:
    """Value the cycle budget, then dispatch at that value. Implements ``DispatchPolicy``.

    :meth:`run` satisfies the protocol and returns the plan alone;
    :meth:`calibrate_and_dispatch` returns the whole :class:`DualSearchResult`,
    which is what a caller wanting the cycle value, the pass count or the dual
    bound should use. The dataclass is frozen, so the result is returned rather
    than stashed on the instance.
    """

    search: DualSearch = SEARCHES[DEFAULT_SEARCH]
    policy: RollingPolicy = field(default_factory=RollingPolicy)

    def run(self, spec: BatterySpec, prices: MarketPrices) -> pd.DataFrame:
        """Dispatch against both price series, from the raw inputs."""
        settlement = build_periods(prices)
        return self.calibrate_and_dispatch(settlement, ModelParameters.from_spec(spec)).plan

    def calibrate_and_dispatch(
        self, settlement: SettlementPeriods, params: ModelParameters
    ) -> DualSearchResult:
        """Run the search over a prepared axis and return everything it found."""
        oracle = CycleOracle(settlement=settlement, params=params, policy=self.policy)
        return self.search.search(oracle)
