"""Building, solving and reading back one window of the settlement.

One window is one call to the solver. The horizon is covered by solving a
sequence of windows that hand their end state to the next
(:mod:`battery_case.modelling.rolling_horizon`); the formulation is the same whether the
window is a day or the whole horizon.

The formulation itself — the objective of §3 and the constraints of §4 — lives
in :mod:`battery_case.modelling.constraints`, one function per section.
:func:`build_problem` only declares the variables and folds those blocks over
the problem, so this module holds how a window is solved, not what it says.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pulp

from battery_case.modelling.constraints import (
    DEFAULT_BLOCKS,
    ConstraintBlock,
    profit_objective,
)
from battery_case.modelling.parameters import ModelParameters
from battery_case.modelling.periods import PERIODS_PER_HOUR, SettlementPeriods
from battery_case.modelling.variables import (
    EMPTY_BATTERY,
    BatteryState,
    DispatchVariables,
    ModelContext,
)


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
    settlement: SettlementPeriods,
    params: ModelParameters,
    state: BatteryState = EMPTY_BATTERY,
    *,
    cycle_value: float = 0.0,
    blocks: tuple[ConstraintBlock, ...] = DEFAULT_BLOCKS,
    solver: pulp.LpSolver | None = None,
) -> WindowSolution:
    """Maximise profit over ``settlement``, starting from ``state``.

    ``cycle_value`` is what one equivalent full cycle is worth, in £, charged
    to the objective so that a window solved in isolation still weighs cycle
    life against the spread in front of it. It is zero in the undecomposed
    model; :func:`battery_case.modelling.cycle_value.searches.calibrate_cycle_value` sets
    it when the cycle budget binds.
    """
    problem, var = build_problem(settlement, params, state, cycle_value=cycle_value, blocks=blocks)
    stats = problem.solve(solver or default_solver(periods=len(settlement)))

    if stats.status is not pulp.LpSolveStatus.Optimal:
        raise RuntimeError(
            f"Window starting {settlement.timestamps[0]} solved as {stats.status.name}"
        )

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
    settlement: SettlementPeriods,
    params: ModelParameters,
    state: BatteryState = EMPTY_BATTERY,
    *,
    cycle_value: float = 0.0,
    blocks: tuple[ConstraintBlock, ...] = DEFAULT_BLOCKS,
) -> tuple[pulp.LpProblem, DispatchVariables]:
    """Assemble the MILP for one window without solving it.

    ``blocks`` are the constraint families to impose, defaulting to the whole of
    §4 (:data:`~battery_case.modelling.constraints.DEFAULT_BLOCKS`). Leaving one
    out solves the model without that constraint, which is how a constraint is
    valued: omitting
    :func:`~battery_case.modelling.constraints.hourly_commitment`, say, gives
    the profit Market 2's hourly commitment (§4.5) costs.
    """
    problem = pulp.LpProblem("battery_dispatch", pulp.LpMaximize)
    ctx = ModelContext.declare(problem, settlement, params, state, cycle_value=cycle_value)

    profit_objective(problem, ctx)
    for block in blocks:
        block(problem, ctx)

    return problem, ctx.var


#: HiGHS settings tuned for a window of this shape, measured in
#: :doc:`solver-parameter-tunning <../../docs/model/solver-parameter-tunning>`.
#:
#: A window is solved at the root: cuts close 99.5% of the integrality gap
#: before any branching, so the node count is 1 and the default heuristic suite
#: spends most of each solve hunting an incumbent the bound has already reached.
#: Switching off the restart, the RINS sub-MIP and the feasibility jump cuts a
#: full pass over the horizon from 435 s to 176 s. These are settings, not
#: relaxations: the binaries of §4.3 and every constraint block stay exactly as
#: they were, and the reference slices of ``tests/test_historical_slices.py``
#: still reproduce their known optima to 6e-11 relative.
#:
#: Two heuristics are deliberately left on, each for its own reason.
#:
#: RENS, because the heuristics do not compose: a 2^4 grid over the four of them
#: puts "all off" at 1.30x against this configuration's 1.82x, the solver still
#: needing one heuristic to produce the incumbent that lets it stop.
#:
#: ``root_reduced_cost``, because switching it off is the one setting measured
#: here that costs real optimality rather than time. It is worth a further 8%
#: (1.96x in the grid), but it puts the 2019-05-11 week 1.7e-5 off its known
#: optimum — outside the 1e-5 those tests allow. Exactness over the last 8%.
#:
#: No gap tolerance is set either: ``gapAbs`` buys under 1% more speed once
#: these are off, and is the other thing that costs money per window.
TUNED_OPTIONS: dict[str, Any] = {
    "mip_allow_restart": False,
    "mip_heuristic_run_rins": False,
    "mip_heuristic_run_feasibility_jump": False,
}


#: Window length, in periods, at which :data:`TUNED_OPTIONS` stops being used.
#:
#: The settings of :data:`TUNED_OPTIONS` are measured on a 96-period window,
#: where the node count is 1 and the heuristics are pure overhead
#: (:doc:`solver-parameter-tunning <../../docs/model/solver-parameter-tunning>`
#: §2). That premise fails as the window grows: a longer program does branch,
#: and then the heuristics it has been denied are what find its incumbent.
#: Measured on one-shot MILPs over real prices, the crossover is sharp and sits
#: right here — tuned against stock, same machine, same data:
#:
#: ===========  ==========  ==========
#: Window       Tuned       Stock
#: ===========  ==========  ==========
#: 7 days       0.9 s       2.5 s
#: 14 days      18.3 s      9.6 s
#: 30 days      *300 s, no proof*  23.4 s
#: ===========  ==========  ==========
#:
#: So a fortnight and up is solved stock. Every window the rolling policy of §6
#: actually poses is 96 periods, far below this, and keeps the tuning.
TUNING_PERIOD_LIMIT = 14 * 24 * PERIODS_PER_HOUR


def default_solver(
    *, time_limit: float | None = None, msg: bool = False, periods: int | None = None
) -> pulp.LpSolver:
    """HiGHS, quiet unless ``msg`` is set, tuned for windows below a fortnight.

    It ships as a dependency and reads the model in process. ``periods`` is the
    length of the program being solved: below :data:`TUNING_PERIOD_LIMIT` it is
    given :data:`TUNED_OPTIONS`, at or above it the stock settings, which are
    faster there by a wide margin. ``None`` means a rolling window and takes the
    tuning. ``msg=True`` lets the HiGHS log through, which is what
    :doc:`tractability <../../docs/model/tractability>` reads its bound
    progression out of.
    """
    tuned = periods is None or periods < TUNING_PERIOD_LIMIT
    return pulp.HiGHS(msg=msg, timeLimit=time_limit, **(TUNED_OPTIONS if tuned else {}))


def _values(variables: list[pulp.LpVariable]) -> np.ndarray:
    return np.array([pulp.value(variable) for variable in variables], dtype=float)
