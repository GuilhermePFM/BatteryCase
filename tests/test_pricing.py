"""The cycle-budget pricers against what each method claims to deliver (§6).

The three-day instance below is the one from ``test_rolling.py``: two modest
days and then a dear one, with a single cycle to spend. The dear day sits beyond
the lookahead, so an unpriced run spends the budget early and a priced one
saves it — which makes the budget bind, and a binding budget is the only case
where a pricer has anything to find.
"""

from __future__ import annotations

from dataclasses import replace

import pulp
import pytest

from battery_case.modelling.bisection import BisectionPricer
from battery_case.modelling.constraints import (
    DEFAULT_BLOCKS,
    RELAXED_BLOCKS,
    cycle_life_cap,
    energy_balance,
    relaxing,
)
from battery_case.modelling.cutting_plane import CuttingPlanePricer, solve_master
from battery_case.modelling.grid import DispatchGrid
from battery_case.modelling.milp import build_problem, default_solver
from battery_case.modelling.parameters import ModelParameters
from battery_case.modelling.pricers import PRICERS, CalibratedDispatcher, pricer_named
from battery_case.modelling.pricing import CycleOracle, DualPoint
from tests.helpers import SPEC, TOLERANCE, assert_feasible, make_grid

#: The whole budget of the instance below, in equivalent full cycles.
BUDGET = 1.0

#: What the dear day alone pays for that one cycle (§6), solved exactly below.
BEST_PROFIT = 1435.79


def _grid() -> DispatchGrid:
    cheap = [20.0] * 24
    return make_grid(cheap + [100.0] * 24 + cheap + [100.0] * 24 + cheap + [400.0] * 24)


def _params() -> ModelParameters:
    return replace(ModelParameters.from_spec(SPEC), cycle_budget=BUDGET)


def _oracle() -> CycleOracle:
    return CycleOracle(grid=_grid(), params=_params())


def _point(price: float, value: float, subgradient: float) -> DualPoint:
    """A cut, with the fields the master does not read left at zero."""
    return DualPoint(
        price=price,
        value=value,
        subgradient=subgradient,
        profit=0.0,
        cycles=0.0,
        schedule=None,  # type: ignore[arg-type]
        relaxed=True,
        feasible=False,
    )


def test_the_relaxed_pass_really_overspends_the_budget() -> None:
    """§6. Pricing a constraint means removing it: a charge of zero must leave
    the horizon free to spend every cycle it can, not clip it at the budget."""
    oracle = _oracle()

    relaxed = oracle.at(0.0, relaxed=True)
    capped = oracle.at(0.0, relaxed=False)

    assert relaxed.cycles == pytest.approx(3.0, abs=1e-3)
    assert relaxed.cycles > capped.cycles
    assert capped.cycles == pytest.approx(BUDGET, rel=1e-4)
    assert not relaxed.feasible
    assert capped.feasible


def test_only_the_relaxed_pass_carries_a_usable_subgradient() -> None:
    """§6. The capped subproblem reports the same clipped count at every charge,
    so its subgradient is zero wherever the budget binds and says nothing."""
    oracle = _oracle()

    for price in (0.0, 100.0):
        assert oracle.at(price, relaxed=False).subgradient == pytest.approx(0.0, abs=1e-3)
        assert oracle.at(price, relaxed=True).subgradient == pytest.approx(-2.0, abs=1e-3)

    # And at the charge that rations the budget exactly, the relaxed slope is zero.
    assert oracle.at(300.0, relaxed=True).subgradient == pytest.approx(0.0, abs=1e-3)


def test_the_oracle_counts_and_reuses_its_passes() -> None:
    """A pass is the unit of cost, so it is counted once and never repeated."""
    oracle = _oracle()

    first = oracle.at(0.0, relaxed=True)
    again = oracle.at(0.0, relaxed=True)
    capped = oracle.at(0.0, relaxed=False)

    assert again is first
    assert capped is not first
    assert oracle.passes == 2


def test_relaxing_builds_a_model_without_the_priced_constraint() -> None:
    assert relaxing(cycle_life_cap) == RELAXED_BLOCKS
    assert cycle_life_cap not in RELAXED_BLOCKS
    assert len(RELAXED_BLOCKS) == len(DEFAULT_BLOCKS) - 1
    assert set(relaxing(cycle_life_cap, energy_balance)) == set(DEFAULT_BLOCKS) - {
        cycle_life_cap,
        energy_balance,
    }


def test_relaxing_rejects_a_block_that_is_not_in_the_model() -> None:
    """A typo must not silently relax nothing."""

    def not_a_constraint(problem: pulp.LpProblem, ctx: object) -> None: ...  # pragma: no cover

    with pytest.raises(ValueError, match="not_a_constraint"):
        relaxing(not_a_constraint)


def test_the_master_minimises_the_envelope_of_its_cuts() -> None:
    """Two cuts crossing at λ = 10: the envelope's minimum is the crossing."""
    falling = _point(price=0.0, value=100.0, subgradient=-2.0)  # L >= 100 - 2 λ
    rising = _point(price=0.0, value=60.0, subgradient=+2.0)  # L >= 60 + 2 λ

    value, price = solve_master([falling, rising], upper_bound=1_000.0)

    assert price == pytest.approx(10.0)
    assert value == pytest.approx(80.0)


def test_the_master_stays_inside_its_box() -> None:
    """A single falling cut would send λ to infinity; the box is what stops it."""
    _, price = solve_master([_point(0.0, 100.0, -2.0)], upper_bound=50.0)

    assert price == pytest.approx(50.0)


def test_both_methods_find_the_schedule_that_spends_the_cycle_best() -> None:
    """§6. The methods differ in passes and in the charge they report, not in
    the dispatch: the deliverable is the dear day, bought cheap and sold at 400."""
    results = {
        name: pricer.price(_oracle())
        for name, pricer in (
            ("bisection", BisectionPricer(upper_bound=5_000.0)),
            ("cutting-plane", CuttingPlanePricer()),
        )
    }

    for name, result in results.items():
        assert result.profit == pytest.approx(BEST_PROFIT, abs=0.01), name
        assert result.cycles <= BUDGET + TOLERANCE, name
        assert_feasible(result.schedule, _params())


def test_bisection_spends_a_fixed_number_of_passes_and_certifies_nothing() -> None:
    result = BisectionPricer(upper_bound=5_000.0, max_iterations=12).price(_oracle())

    assert result.passes == 13
    assert result.bound is None
    assert result.price > BEST_PROFIT / 2  # the top of the plateau, not a shadow price


def test_cutting_planes_close_their_gap_in_fewer_passes_and_report_a_bound() -> None:
    result = CuttingPlanePricer().price(_oracle())

    assert result.passes < 13
    assert result.bound is not None
    assert result.bound.relative_gap <= CuttingPlanePricer().tolerance
    assert result.bound.gap >= -TOLERANCE


def test_the_dual_bound_is_not_below_the_exact_optimum() -> None:
    """§6 weak duality, which is the whole claim the bound makes. The instance is
    small enough to solve whole, as one capped MILP, so the claim is checkable."""
    grid, params = _grid(), _params()
    problem, _ = build_problem(grid, params)
    problem.solve(default_solver())
    objective = pulp.value(problem.objective)
    assert objective is not None
    exact = float(objective)

    result = CuttingPlanePricer().price(CycleOracle(grid=grid, params=params))

    assert result.bound is not None
    assert result.bound.value >= exact - TOLERANCE
    assert result.profit <= exact + TOLERANCE


def test_an_ample_budget_costs_one_pass_under_either_method() -> None:
    """§6. With the budget of §5 the cap never binds, so there is nothing to
    search for: the first pass says so and both methods stop."""
    grid = _grid()
    params = ModelParameters.from_spec(SPEC)  # the full 5,000 cycles

    for name, pricer in PRICERS.items():
        result = pricer.price(CycleOracle(grid=grid, params=params))
        assert result.price == 0.0, name
        assert result.passes == 1, name
        assert result.cycles < params.cycle_budget, name


def test_a_calibrated_dispatcher_is_a_dispatcher() -> None:
    """The seam downstream does not change: prices in, schedule out."""
    dispatcher = CalibratedDispatcher(pricer=pricer_named("cutting-plane"))
    result = dispatcher.price_and_dispatch(_grid(), _params())

    assert result.profit == pytest.approx(BEST_PROFIT, abs=0.01)
    assert list(result.schedule.columns) == list(
        CalibratedDispatcher().price_and_dispatch(_grid(), _params()).schedule.columns
    )


def test_an_unknown_method_names_the_ones_there_are() -> None:
    with pytest.raises(KeyError, match="cutting-plane"):
        pricer_named("gradient-descent")
