"""The model against known optima on slices of the supplied price history.

Every other test poses the model on a hand-built price shape, where the right
answer is obvious by construction. These tests do the opposite: they run the
model on *real* days and weeks of Attachment 2 and check it reaches the profit
an exact solve of that slice says is available.

The slices were drawn at random, once, and then frozen: five single days and
three whole weeks, spread across the three years of the horizon. Each carries
the optimal profit over that slice, in £, as its own reference value.

Two things are being checked, and they are separate claims:

* ``test_rolling_dispatch_reaches_the_known_optimum`` runs the model as the CLI
  runs it — :class:`RollingPolicy`, committing a day at a time — and asserts the
  profit equals the frozen optimum. This is the claim that the decomposition of
  §6 costs nothing on these slices: a day-ahead lookahead is enough to see the
  spreads that matter.
* ``test_frozen_optimum_still_solves_as_the_optimum`` re-derives that optimum
  from the slice as a single MILP, solved to a near-zero gap, so the reference
  values cannot rot quietly behind a change to the formulation. It is the slow
  one, and it is the reason the first test may assert equality rather than a
  bound.

The slices start from an empty battery and end wherever the dispatch leaves
them, so each is a self-contained problem; the 5,000-cycle budget of §5 does not
bind over a week and plays no part here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd
import pulp
import pytest

from battery_case.data_io.loaders import load_battery_spec, load_market_prices
from battery_case.data_io.paths import BATTERY_SPEC_XLSX, MARKET_PRICES_XLSX
from battery_case.modelling.parameters import ModelParameters
from battery_case.modelling.periods import SettlementPeriods, build_periods
from battery_case.modelling.plan import summarise
from battery_case.modelling.rolling_horizon import PERIODS_PER_DAY, RollingPolicy
from battery_case.modelling.window_problem import build_problem
from tests.helpers import TOLERANCE, assert_feasible

pytestmark = pytest.mark.skipif(
    not (BATTERY_SPEC_XLSX.exists() and MARKET_PRICES_XLSX.exists()),
    reason="raw spreadsheets are not present",
)

#: How close the dispatch must come to the frozen optimum, relative to it.
#:
#: Tighter than HiGHS's own default relative MIP gap of 1e-4, because on these
#: slices the solver closes the gap entirely. A failure at this tolerance but
#: inside 1e-4 is the solver stopping early, not the model losing money; a
#: failure outside it is a dispatch that is genuinely no longer optimal.
_OPTIMALITY_RTOL = 1e-5

#: The gap the reference solve is held to, so "optimal" means optimal.
_REFERENCE_GAP = 1e-9


@dataclass(frozen=True, slots=True)
class Slice:
    """A stretch of the real horizon and the profit obtainable over it."""

    start: str
    days: int
    optimum_gbp: float

    @property
    def periods(self) -> int:
        return self.days * PERIODS_PER_DAY

    def __str__(self) -> str:
        return f"{self.start}+{self.days}d"


#: Five single days, drawn at random from the 1,096 in the horizon.
DAYS = (
    Slice("2018-07-30", 1, 146.393602),
    Slice("2018-09-27", 1, 175.420018),
    Slice("2019-01-29", 1, 86.251983),
    Slice("2019-06-10", 1, 150.220115),
    Slice("2020-02-11", 1, 225.902136),
)

#: Three whole weeks, drawn the same way.
WEEKS = (
    Slice("2018-02-15", 7, 1176.770225),
    Slice("2019-05-11", 7, 903.457632),
    Slice("2019-09-26", 7, 1332.937652),
)

SLICES = DAYS + WEEKS


@pytest.fixture(scope="module")
def params() -> ModelParameters:
    """Attachment 1, as the CLI reads it."""
    return ModelParameters.from_spec(load_battery_spec())


@pytest.fixture(scope="module")
def settlement() -> SettlementPeriods:
    """The whole horizon on the common half-hourly settlement, read once."""
    return build_periods(load_market_prices())


def cut(settlement: SettlementPeriods, case: Slice) -> SettlementPeriods:
    """The sub-settlement a case names, by day boundary.

    Sliced by position rather than by label: every day of the horizon holds
    exactly 48 Market 1 rows, which the clock-change labels do not (§ the
    module docstring of :mod:`battery_case.modelling.periods`).
    """
    start = int(settlement.timestamps.searchsorted(case.start))
    assert start % PERIODS_PER_DAY == 0, f"{case.start} is not a day boundary"
    window = settlement.window(start, case.periods)
    assert len(window) == case.periods, f"{case} runs past the end of the horizon"
    return window


@pytest.fixture(scope="module")
def dispatch(
    settlement: SettlementPeriods, params: ModelParameters
) -> Callable[[Slice], pd.DataFrame]:
    """Dispatch a slice the way the CLI does, solving each slice only once."""
    plans: dict[Slice, pd.DataFrame] = {}

    def run(case: Slice) -> pd.DataFrame:
        if case not in plans:
            plans[case] = RollingPolicy().dispatch(cut(settlement, case), params)
        return plans[case]

    return run


@pytest.mark.parametrize("case", SLICES, ids=str)
def test_rolling_dispatch_reaches_the_known_optimum(
    case: Slice,
    dispatch: Callable[[Slice], pd.DataFrame],
    settlement: SettlementPeriods,
    params: ModelParameters,
) -> None:
    plan = dispatch(case)

    assert_feasible(plan, params)
    assert plan.index.equals(cut(settlement, case).timestamps)
    assert float(plan["net_revenue_gbp"].sum()) == pytest.approx(
        case.optimum_gbp, rel=_OPTIMALITY_RTOL
    )


@pytest.mark.parametrize("case", SLICES, ids=str)
def test_summary_reconciles_with_the_known_optimum(
    case: Slice, dispatch: Callable[[Slice], pd.DataFrame], params: ModelParameters
) -> None:
    """The headline figures of §7 add up to the same profit, by a second route."""
    plan = dispatch(case)
    summary = summarise(plan, params)

    assert summary["profit_gbp"] == pytest.approx(case.optimum_gbp, rel=_OPTIMALITY_RTOL)
    assert summary["income_gbp"] - summary["cost_gbp"] == pytest.approx(
        summary["profit_gbp"], abs=1e-6
    )
    assert summary["net_revenue_market_1_gbp"] + summary["net_revenue_market_2_gbp"] == (
        pytest.approx(summary["profit_gbp"], abs=1e-6)
    )
    assert summary["cycles_used"] <= params.cycle_budget
    assert summary["final_storage_mwh"] == plan["storage_mwh"].iloc[-1]
    assert summary["final_storage_mwh"] <= summary["final_usable_volume_mwh"] + TOLERANCE


@pytest.mark.parametrize("case", SLICES, ids=str)
def test_energy_left_in_the_store_was_never_paid_for(
    case: Slice, dispatch: Callable[[Slice], pd.DataFrame]
) -> None:
    """A slice may end charged, but only where the market paid it to charge.

    Energy still in the store when the horizon ends is never sold, so buying it
    at a positive price would be a straight loss and an optimal plan would not
    do it. Anything bought after the last discharge must therefore have come at
    a price of zero or less — which is the only reason a plan ends with volume.
    """
    plan = dispatch(case)

    if plan["storage_mwh"].iloc[-1] <= TOLERANCE:
        return

    discharged = plan["discharge_1_mw"] + plan["discharge_2_mw"]
    last_sale = int((discharged > TOLERANCE).to_numpy().nonzero()[0][-1])
    assert (plan["net_revenue_gbp"].iloc[last_sale + 1 :] >= -TOLERANCE).all()


@pytest.mark.slow
@pytest.mark.parametrize("case", SLICES, ids=str)
def test_frozen_optimum_still_solves_as_the_optimum(
    case: Slice, settlement: SettlementPeriods, params: ModelParameters
) -> None:
    """Re-derive each reference value as one MILP over the whole slice."""
    problem, _ = build_problem(cut(settlement, case), params)

    stats = problem.solve(pulp.HiGHS(msg=False, gapRel=0.0, gapAbs=_REFERENCE_GAP))

    assert stats.status is pulp.LpSolveStatus.Optimal
    assert pulp.value(problem.objective) == pytest.approx(case.optimum_gbp, abs=1e-5)
