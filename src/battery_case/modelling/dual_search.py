"""The search methods on offer, by the name that selects one (§6).

:data:`SEARCHES` is the catalogue: one entry per method, keyed by the name the
CLI accepts. The key *is* the name — no method carries a name of its own —
so the registry is the single place a method is announced.
:data:`DEFAULT_SEARCH` names the one used when a caller asks for a calibrated
run without saying which method: cutting planes, which costs fewer passes and
returns a dual bound, where bisection reads one bit per pass and certifies
nothing.

A search is run over the horizon by
:class:`~battery_case.modelling.dual_problem.CycleOracle`; it reaches the CLI as
a policy through
:class:`~battery_case.modelling.calibrated_policy.CalibratedPolicy`.
"""

from __future__ import annotations

import pandas as pd

from battery_case.modelling.bisection import BisectionSearch
from battery_case.modelling.cutting_plane import CuttingPlaneSearch
from battery_case.modelling.dual_problem import CycleOracle, DualSearch
from battery_case.modelling.parameters import ModelParameters
from battery_case.modelling.periods import SettlementPeriods
from battery_case.modelling.rolling_horizon import RollingPolicy

#: The search methods, by the name the CLI takes. See §6 for both.
SEARCHES: dict[str, DualSearch] = {
    "cutting-plane": CuttingPlaneSearch(),
    "bisection": BisectionSearch(),
}

#: The method a calibrated run uses when none is named (§6).
DEFAULT_SEARCH = "cutting-plane"


def calibrate_cycle_value(
    settlement: SettlementPeriods,
    params: ModelParameters,
    *,
    policy: RollingPolicy | None = None,
    upper_bound: float = 200.0,
    tolerance: float = 1e-3,
    max_iterations: int = 12,
) -> tuple[float, pd.DataFrame]:
    """Find the value per cycle that rations a binding cycle budget, by bisection.

    The narrow door onto
    :class:`~battery_case.modelling.bisection.BisectionSearch`, for a caller
    that wants that method and nothing else from the seam. A calibrated run
    should go through :data:`SEARCHES` or
    :class:`~battery_case.modelling.calibrated_policy.CalibratedPolicy` instead,
    which default to :data:`DEFAULT_SEARCH` and can return a dual bound.
    """
    search = BisectionSearch(
        upper_bound=upper_bound, tolerance=tolerance, max_iterations=max_iterations
    )
    oracle = CycleOracle(
        settlement=settlement,
        params=params,
        policy=policy if policy is not None else RollingPolicy(),
    )
    result = search.search(oracle)
    return result.cycle_value, result.plan


def search_named(name: str) -> DualSearch:
    """The search ``name`` from :data:`SEARCHES`, with its default settings.

    Raises :class:`KeyError` naming the methods available, so a typo reads as a
    list of choices rather than a traceback. A method with different settings is
    built from its own class — the registry holds the defaults, not the only
    configuration.
    """
    if name not in SEARCHES:
        raise KeyError(f"unknown search method {name!r}; available: {', '.join(SEARCHES)}")
    return SEARCHES[name]
