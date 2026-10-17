"""The pricing methods on offer, and the way a priced run reaches the CLI (§6).

:data:`PRICERS` is the catalogue: one entry per method, keyed by the name the
CLI accepts. The key *is* the name — no method carries a name of its own —
so the registry is the single place a method is announced.

:class:`CalibratedDispatcher` adapts a pricer to the ``Dispatcher`` protocol, so
that a priced run is still "prices in, schedule out" as far as
:func:`~battery_case.modelling.schedule.summarise`, the CLI and the notebooks
are concerned.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from battery_case.data_models import BatterySpec, MarketPrices
from battery_case.modelling.bisection import BisectionPricer
from battery_case.modelling.cutting_plane import CuttingPlanePricer
from battery_case.modelling.grid import DispatchGrid, build_grid
from battery_case.modelling.parameters import ModelParameters
from battery_case.modelling.pricing import CycleOracle, CyclePricer, PricingResult
from battery_case.modelling.rolling import RollingDispatcher

#: The pricing methods, by the name the CLI takes. See §6 for both.
PRICERS: dict[str, CyclePricer] = {
    "bisection": BisectionPricer(),
    "cutting-plane": CuttingPlanePricer(),
}


@dataclass(frozen=True, slots=True)
class CalibratedDispatcher:
    """Price the cycle budget, then dispatch at that price. Implements ``Dispatcher``.

    :meth:`run` satisfies the protocol and returns the schedule alone;
    :meth:`price_and_dispatch` returns the whole :class:`PricingResult`, which
    is what a caller wanting the charge, the pass count or the dual bound should
    use. The dataclass is frozen, so the result is returned rather than stashed
    on the instance.
    """

    pricer: CyclePricer = PRICERS["bisection"]
    dispatcher: RollingDispatcher = field(default_factory=RollingDispatcher)

    def run(self, spec: BatterySpec, prices: MarketPrices) -> pd.DataFrame:
        """Dispatch against both price series, from the raw inputs."""
        grid = build_grid(prices)
        return self.price_and_dispatch(grid, ModelParameters.from_spec(spec)).schedule

    def price_and_dispatch(self, grid: DispatchGrid, params: ModelParameters) -> PricingResult:
        """Run the search over a prepared grid and return everything it found."""
        oracle = CycleOracle(grid=grid, params=params, dispatcher=self.dispatcher)
        return self.pricer.price(oracle)


def calibrate_cycle_price(
    grid: DispatchGrid,
    params: ModelParameters,
    *,
    dispatcher: RollingDispatcher | None = None,
    upper_bound: float = 200.0,
    tolerance: float = 1e-3,
    max_iterations: int = 12,
) -> tuple[float, pd.DataFrame]:
    """Find the charge per cycle that rations a binding cycle budget, by bisection.

    Kept as the narrow door the §6 narrative and its tests already use:
    :class:`~battery_case.modelling.bisection.BisectionPricer` behind the
    signature this project had before the methods became interchangeable. New
    callers should go through :data:`PRICERS` or
    :class:`CalibratedDispatcher`, which can also return a dual bound.
    """
    pricer = BisectionPricer(
        upper_bound=upper_bound, tolerance=tolerance, max_iterations=max_iterations
    )
    oracle = CycleOracle(
        grid=grid,
        params=params,
        dispatcher=dispatcher if dispatcher is not None else RollingDispatcher(),
    )
    result = pricer.price(oracle)
    return result.price, result.schedule


def pricer_named(name: str) -> CyclePricer:
    """The pricer ``name`` from :data:`PRICERS`, with its default settings.

    Raises :class:`KeyError` naming the methods available, so a typo reads as a
    list of choices rather than a traceback. A method with different settings is
    built from its own class — the registry holds the defaults, not the only
    configuration.
    """
    if name not in PRICERS:
        raise KeyError(f"unknown pricing method {name!r}; available: {', '.join(PRICERS)}")
    return PRICERS[name]
