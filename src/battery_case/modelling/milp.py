"""Building, solving and reading back one window of the grid.

One window is one call to the solver. The horizon is covered by solving a
sequence of windows that hand their end state to the next
(:mod:`battery_case.modelling.rolling`); the formulation is the same whether the
window is a day or the whole horizon.

The formulation itself — the objective of §3 and the constraints of §4 — lives
in :mod:`battery_case.modelling.constraints`, one function per section.
:func:`build_problem` only declares the variables and folds those blocks over
the problem, so this module holds how a window is solved, not what it says.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pulp

from battery_case.modelling.constraints import (
    DEFAULT_BLOCKS,
    EMPTY_BATTERY,
    BatteryState,
    ConstraintBlock,
    DispatchVariables,
    ModelContext,
    profit_objective,
)
from battery_case.modelling.grid import DispatchGrid
from battery_case.modelling.parameters import ModelParameters


@dataclass(frozen=True, slots=True)
class WindowSolution:
    """Optimal decisions for one window, period by period."""

    charge_1_mw: np.ndarray
    charge_2_mw: np.ndarray
    discharge_1_mw: np.ndarray
    discharge_2_mw: np.ndarray
    storage_mwh: np.ndarray
    cycles: np.ndarray
    status: str

    def __len__(self) -> int:
        return len(self.charge_1_mw)

    def state_after(self, periods: int) -> BatteryState:
        """State carried forward after the first ``periods`` periods are kept."""
        last = periods - 1
        return BatteryState(storage_mwh=self.storage_mwh[last], cycles=self.cycles[last])


def solve_window(
    grid: DispatchGrid,
    params: ModelParameters,
    state: BatteryState = EMPTY_BATTERY,
    *,
    cycle_price: float = 0.0,
    blocks: tuple[ConstraintBlock, ...] = DEFAULT_BLOCKS,
    solver: pulp.LpSolver | None = None,
) -> WindowSolution:
    """Maximise profit over ``grid``, starting from ``state``.

    ``cycle_price`` is a charge in £ per equivalent full cycle used, added to
    the objective so that a window solved in isolation still weighs cycle life
    against the spread in front of it. It is zero in the undecomposed model;
    :func:`battery_case.modelling.rolling.calibrate_cycle_price` sets it when
    the cycle budget binds.
    """
    problem, var = build_problem(grid, params, state, cycle_price=cycle_price, blocks=blocks)
    stats = problem.solve(solver if solver is not None else default_solver())

    if stats.status is not pulp.LpSolveStatus.Optimal:
        raise RuntimeError(f"Window starting {grid.timestamps[0]} solved as {stats.status.name}")

    return WindowSolution(
        charge_1_mw=_values(var.c1),
        charge_2_mw=_values(var.c2),
        discharge_1_mw=_values(var.d1),
        discharge_2_mw=_values(var.d2),
        storage_mwh=_values(var.storage),
        cycles=_values(var.n_cyc),
        status=stats.status.name,
    )


def build_problem(
    grid: DispatchGrid,
    params: ModelParameters,
    state: BatteryState = EMPTY_BATTERY,
    *,
    cycle_price: float = 0.0,
    blocks: tuple[ConstraintBlock, ...] = DEFAULT_BLOCKS,
) -> tuple[pulp.LpProblem, DispatchVariables]:
    """Assemble the MILP for one window without solving it.

    ``blocks`` are the constraint families to impose, defaulting to the whole of
    §4 (:data:`~battery_case.modelling.constraints.DEFAULT_BLOCKS`). Leaving one
    out solves the model without that constraint, which is how a constraint is
    priced: omitting
    :func:`~battery_case.modelling.constraints.hourly_commitment`, say, gives
    the profit Market 2's hourly commitment (§4.5) costs.
    """
    problem = pulp.LpProblem("battery_dispatch", pulp.LpMaximize)
    ctx = ModelContext.declare(problem, grid, params, state, cycle_price=cycle_price)

    profit_objective(problem, ctx)
    for block in blocks:
        block(problem, ctx)

    return problem, ctx.var


def default_solver(*, time_limit: float | None = None) -> pulp.LpSolver:
    """HiGHS, quietly. It ships as a dependency and reads the model in process."""
    return pulp.HiGHS(msg=False, timeLimit=time_limit)


def _values(variables: list[pulp.LpVariable]) -> np.ndarray:
    return np.array([pulp.value(variable) for variable in variables], dtype=float)
