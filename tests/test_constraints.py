"""Each constraint block against the rows it is meant to add (§3 to §4.7).

These tests never call a solver: a block's job is to put named rows on the
problem, and that is what is asserted here. The solved behaviour each block
produces is covered in ``test_milp.py``.
"""

from __future__ import annotations

import math

import pulp
import pytest

from battery_case.modelling.constraints import (
    DEFAULT_BLOCKS,
    ConstraintBlock,
    DispatchVariables,
    ModelContext,
    cycle_accounting,
    cycle_life_cap,
    effective_volume,
    energy_balance,
    hourly_commitment,
    mode_exclusivity,
    profit_objective,
)
from battery_case.modelling.grid import DispatchGrid
from battery_case.modelling.milp import build_problem
from battery_case.modelling.parameters import ModelParameters
from tests.helpers import SPEC, make_grid

#: Four hours of half-hourly periods — long enough for §4.5 to bite.
PERIODS = 8


def _params() -> ModelParameters:
    return ModelParameters.from_spec(SPEC)


def _grid(periods: int = PERIODS) -> DispatchGrid:
    return make_grid([10.0] * periods)


def _context(grid: DispatchGrid) -> tuple[pulp.LpProblem, ModelContext]:
    """A problem with the variables declared on it, and nothing else."""
    problem = pulp.LpProblem("block_under_test", pulp.LpMaximize)
    return problem, ModelContext.declare(problem, grid, _params())


def _rows(block: ConstraintBlock, grid: DispatchGrid | None = None) -> list[str]:
    """The names of the rows ``block`` adds to a fresh problem."""
    problem, ctx = _context(grid if grid is not None else _grid())
    block(problem, ctx)
    return [constraint.name for constraint in problem.constraints()]


def test_variables_are_declared_with_the_bounds_of_the_spec() -> None:
    """§2, §4.1. The volume and rate caps are variable bounds."""
    params = _params()
    problem = pulp.LpProblem("vars", pulp.LpMaximize)
    var = DispatchVariables.declare(problem, range(PERIODS), params)

    assert var.c1[0].upBound == params.max_charge_mw
    assert var.d1[0].upBound == params.max_discharge_mw
    assert var.storage[0].upBound == params.nominal_volume_mwh
    assert var.charging[0].cat != "Continuous"


def test_the_cycle_count_is_left_free_so_that_its_cap_can_be_relaxed() -> None:
    """§4.6. The budget is a row, not a bound: as a bound it would clip the count
    even with :func:`cycle_life_cap` omitted, and the relaxation of §6 — which
    prices the budget by removing it — would relax nothing."""
    problem = pulp.LpProblem("vars", pulp.LpMaximize)
    var = DispatchVariables.declare(problem, range(PERIODS), _params())

    assert var.n_cyc[0].upBound == math.inf
    assert var.n_cyc[0].lowBound == 0
    for variables in (var.c1, var.c2, var.d1, var.d2, var.storage, var.n_cyc, var.charging):
        assert len(variables) == PERIODS
        assert variables[0].lowBound == 0


def test_the_context_carries_the_opening_state_into_the_first_period() -> None:
    """§4.2, §4.6. Only period 0 reads the handover; the rest read period t-1."""
    _, ctx = _context(_grid())

    assert ctx.previous_storage(0) == ctx.state.storage_mwh
    assert ctx.previous_cycles(0) == ctx.state.cycles
    assert ctx.previous_storage(1) is ctx.var.storage[0]
    assert ctx.previous_cycles(1) is ctx.var.n_cyc[0]
    assert ctx.keep_charged == pytest.approx(0.95)
    assert ctx.delivered == pytest.approx(0.95)


def test_energy_balance_adds_one_row_per_period() -> None:
    """§4.2."""
    assert _rows(energy_balance) == [f"balance_{t}" for t in range(PERIODS)]


def test_cycle_accounting_adds_one_row_per_period() -> None:
    """§4.6."""
    assert _rows(cycle_accounting) == [f"cycles_{t}" for t in range(PERIODS)]


def test_effective_volume_adds_one_row_per_period() -> None:
    """§4.1 with §4.7 substituted in."""
    assert _rows(effective_volume) == [f"storage_bound_{t}" for t in range(PERIODS)]


def test_mode_exclusivity_adds_a_rate_row_on_each_side() -> None:
    """§4.3."""
    assert set(_rows(mode_exclusivity)) == {
        name for t in range(PERIODS) for name in (f"charge_rate_{t}", f"discharge_rate_{t}")
    }


def test_hourly_commitment_ties_each_hour_to_its_first_half() -> None:
    """§4.5. The row is between t and t-1, so only the second half hour has one."""
    rows = _rows(hourly_commitment)

    assert set(rows) == {
        name
        for t in range(1, PERIODS, 2)
        for name in (f"hourly_charge_{t}", f"hourly_discharge_{t}")
    }
    assert len(rows) == PERIODS  # two rows per hour, four hours


def test_hourly_commitment_adds_nothing_within_a_single_hour() -> None:
    """§4.5. A one-hour window has nothing to tie its two half hours to."""
    assert _rows(hourly_commitment, _grid(periods=2)) == ["hourly_charge_1", "hourly_discharge_1"]


def test_cycle_life_cap_adds_one_row_for_the_window() -> None:
    """§4.6. The budget is one number for the whole horizon, so one row."""
    assert _rows(cycle_life_cap) == ["cycle_life"]


def test_the_objective_is_the_only_thing_the_objective_block_adds() -> None:
    """§3. The objective is not a constraint and must add no rows."""
    problem, ctx = _context(_grid())
    profit_objective(problem, ctx)

    assert problem.constraints() == []
    assert problem.objective is not None


def test_the_default_blocks_account_for_every_row_of_the_model() -> None:
    """A block dropped from the registry is a constraint silently lost."""
    grid = _grid()
    problem, _ = build_problem(grid, _params())
    assembled = {constraint.name for constraint in problem.constraints()}

    from_blocks = {name for block in DEFAULT_BLOCKS for name in _rows(block, grid)}
    assert from_blocks == assembled


def test_omitting_every_block_leaves_an_objective_and_no_constraints() -> None:
    """``blocks`` is the only source of rows, which is what makes it a lever:
    dropping one prices the constraint it imposes."""
    problem, var = build_problem(_grid(), _params(), blocks=())

    assert problem.constraints() == []
    assert problem.objective is not None
    assert len(var.storage) == PERIODS
