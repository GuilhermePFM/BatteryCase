"""The formulation of §3 to §4.7: the objective, and one block per constraint.

Each section of the write-up is a function that takes the problem and a
:class:`ModelContext` and adds its own rows, naming them as the write-up does.
:func:`~battery_case.modelling.milp.build_problem` folds :data:`DEFAULT_BLOCKS`
over the problem, so the formulation is a list of sections rather than one body,
and a section can be read, tested, or left out on its own.

Two formulation choices are visible here. The effective volume S_max(t) is
substituted out rather than carried as a variable, as §4.7 permits, so §4.1
becomes one row per period in :func:`effective_volume`. And §4.4 is implied by
§4.1 and §4.2 together, so no block restates it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pulp

from battery_case.modelling.grid import PERIODS_PER_HOUR, DispatchGrid
from battery_case.modelling.parameters import ModelParameters


@dataclass(frozen=True, slots=True)
class BatteryState:
    """The state the energy balance (§4.2) and cycle count (§4.6) carry forward.

    ``storage_mwh`` is ``S(t-1)`` and ``cycles`` is ``n_cyc(t-1)`` for the first
    period of a window. The battery starts empty and unused, per §4.2 and §4.6.
    """

    storage_mwh: float = 0.0
    cycles: float = 0.0


#: A battery that has not yet charged or discharged: S(0) = 0, n_cyc(0) = 0.
EMPTY_BATTERY = BatteryState()


@dataclass(frozen=True, slots=True)
class DispatchVariables:
    """The decision variables of §2, one list per symbol, indexed by period."""

    c1: list[pulp.LpVariable]
    c2: list[pulp.LpVariable]
    d1: list[pulp.LpVariable]
    d2: list[pulp.LpVariable]
    storage: list[pulp.LpVariable]
    n_cyc: list[pulp.LpVariable]
    charging: list[pulp.LpVariable]

    @classmethod
    def declare(
        cls, problem: pulp.LpProblem, periods: range, params: ModelParameters
    ) -> DispatchVariables:
        """Add the variables to ``problem``, bounded by the spec (§2, §4.1, §4.6)."""
        return cls(
            c1=problem.add_variable_matrix("c1", periods, 0, params.max_charge_mw),
            c2=problem.add_variable_matrix("c2", periods, 0, params.max_charge_mw),
            d1=problem.add_variable_matrix("d1", periods, 0, params.max_discharge_mw),
            d2=problem.add_variable_matrix("d2", periods, 0, params.max_discharge_mw),
            storage=problem.add_variable_matrix("S", periods, 0, params.nominal_volume_mwh),
            n_cyc=problem.add_variable_matrix("n_cyc", periods, 0, params.cycle_budget),
            charging=problem.add_variable_matrix("u", periods, cat="Binary"),
        )


@dataclass(frozen=True, slots=True)
class ModelContext:
    """Everything a block reads: the data, the variables, and the state before them.

    The derived quantities of §4.2 are properties here so that each block reads
    like the write-up without recomputing them.
    """

    grid: DispatchGrid
    params: ModelParameters
    state: BatteryState
    var: DispatchVariables
    cycle_price: float = 0.0

    @classmethod
    def declare(
        cls,
        problem: pulp.LpProblem,
        grid: DispatchGrid,
        params: ModelParameters,
        state: BatteryState = EMPTY_BATTERY,
        *,
        cycle_price: float = 0.0,
    ) -> ModelContext:
        """Declare the variables on ``problem`` and bundle them with the data."""
        periods = range(len(grid))
        return cls(
            grid=grid,
            params=params,
            state=state,
            var=DispatchVariables.declare(problem, periods, params),
            cycle_price=cycle_price,
        )

    @property
    def periods(self) -> range:
        """The period indices of the window."""
        return range(len(self.grid))

    @property
    def keep_charged(self) -> float:
        """``1 - e_c``: the share of imported energy that reaches the store (§4.2)."""
        return 1.0 - self.params.charge_loss

    @property
    def delivered(self) -> float:
        """``1 - e_d``: the share of discharged energy that is sold (§3, §4.2)."""
        return 1.0 - self.params.discharge_loss

    def previous_storage(self, t: int) -> pulp.LpVariable | float:
        """``S(t-1)``, or the state handed over for the first period."""
        return self.var.storage[t - 1] if t else self.state.storage_mwh

    def previous_cycles(self, t: int) -> pulp.LpVariable | float:
        """``n_cyc(t-1)``, or the state handed over for the first period."""
        return self.var.n_cyc[t - 1] if t else self.state.cycles


#: A constraint family: adds its own rows to the problem, reads nothing back.
ConstraintBlock = Callable[[pulp.LpProblem, ModelContext], None]


def profit_objective(problem: pulp.LpProblem, ctx: ModelContext) -> None:
    """§3 objective: energy delivered at each market's price, less energy bought.

    ``ctx.cycle_price`` is a charge in £ per equivalent full cycle used, so that
    a window solved in isolation still weighs cycle life against the spread in
    front of it. It is zero in the undecomposed model.
    """
    var = ctx.var
    dt = ctx.params.dt
    cycles_used = var.n_cyc[-1] - ctx.state.cycles

    problem += (
        pulp.lpSum(
            dt
            * (
                ctx.grid.price_1[t] * (ctx.delivered * var.d1[t] - var.c1[t])
                + ctx.grid.price_2[t] * (ctx.delivered * var.d2[t] - var.c2[t])
            )
            for t in ctx.periods
        )
        - ctx.cycle_price * cycles_used
    )


def energy_balance(problem: pulp.LpProblem, ctx: ModelContext) -> None:
    """§4.2 energy balance. Charging is lossy into the store; discharging debits
    the full d, the discharge loss being taken in the objective."""
    var = ctx.var
    for t in ctx.periods:
        problem += (
            var.storage[t]
            == ctx.previous_storage(t)
            + ctx.params.dt * (ctx.keep_charged * (var.c1[t] + var.c2[t]) - var.d1[t] - var.d2[t]),
            f"balance_{t}",
        )


def cycle_accounting(problem: pulp.LpProblem, ctx: ModelContext) -> None:
    """§4.6 equivalent full cycles, counted on the discharge side only."""
    var = ctx.var
    for t in ctx.periods:
        problem += (
            var.n_cyc[t]
            == ctx.previous_cycles(t)
            + ctx.params.dt * (var.d1[t] + var.d2[t]) / ctx.params.nominal_volume_mwh,
            f"cycles_{t}",
        )


def effective_volume(problem: pulp.LpProblem, ctx: ModelContext) -> None:
    """§4.1 with §4.7 substituted in: S(t) <= S_max(t) = volume (1 - rho n(t))."""
    volume = ctx.params.nominal_volume_mwh
    for t in ctx.periods:
        problem += (
            ctx.var.storage[t] + volume * ctx.params.degradation_per_cycle * ctx.var.n_cyc[t]
            <= volume,
            f"storage_bound_{t}",
        )


def mode_exclusivity(problem: pulp.LpProblem, ctx: ModelContext) -> None:
    """§4.3 charge or discharge, not both, and the rate limits with it."""
    var = ctx.var
    for t in ctx.periods:
        problem += (
            var.c1[t] + var.c2[t] <= ctx.params.max_charge_mw * var.charging[t],
            f"charge_rate_{t}",
        )
        problem += (
            var.d1[t] + var.d2[t] <= ctx.params.max_discharge_mw * (1 - var.charging[t]),
            f"discharge_rate_{t}",
        )


def hourly_commitment(problem: pulp.LpProblem, ctx: ModelContext) -> None:
    """§4.5 Market 2 is committed for its whole hourly interval."""
    var = ctx.var
    for t in ctx.periods:
        if t % PERIODS_PER_HOUR:
            problem += var.c2[t] - var.c2[t - 1] == 0, f"hourly_charge_{t}"
            problem += var.d2[t] - var.d2[t - 1] == 0, f"hourly_discharge_{t}"


def cycle_life_cap(problem: pulp.LpProblem, ctx: ModelContext) -> None:
    """§4.6 cycle life.

    The cap is already the upper bound of every ``n_cyc(t)`` variable, which is
    the same constraint: n_cyc is non-decreasing, so the two forms are
    equivalent while the budget is one number for the whole horizon. This row is
    redundant, and kept so a solver log naming it points at the section.
    """
    problem += ctx.var.n_cyc[-1] <= ctx.params.cycle_budget, "cycle_life"


#: The constraints of §4, in the order the write-up states them.
DEFAULT_BLOCKS: tuple[ConstraintBlock, ...] = (
    energy_balance,  # §4.2
    cycle_accounting,  # §4.6
    effective_volume,  # §4.1 + §4.7
    mode_exclusivity,  # §4.3
    hourly_commitment,  # §4.5
    cycle_life_cap,  # §4.6
)
