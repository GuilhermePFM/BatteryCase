"""The formulation of §3 to §4.7: the objective, and one block per constraint.

Each section of the write-up is a function that takes the problem and a
:class:`~battery_case.modelling.variables.ModelContext` and adds its own rows,
naming them as the write-up does.
:func:`~battery_case.modelling.window_problem.build_problem` folds
:data:`DEFAULT_BLOCKS` over the problem, so the formulation is a list of
sections rather than one body, and a section can be read, tested, or left out
on its own. The variables and the state the blocks read are declared in
:mod:`battery_case.modelling.variables`.

Two formulation choices are visible here. The effective volume S_max(t) is
substituted out rather than carried as a variable, as §4.7 permits, so §4.1
becomes one row per period in :func:`volume_limit`. And §4.4 is implied by
§4.1 and §4.2 together, so no block restates it.
"""

from __future__ import annotations

from collections.abc import Callable

import pulp

from battery_case.modelling.periods import PERIODS_PER_HOUR
from battery_case.modelling.variables import ModelContext

#: A constraint family: adds its own rows to the problem, reads nothing back.
ConstraintBlock = Callable[[pulp.LpProblem, ModelContext], None]


def profit_objective(problem: pulp.LpProblem, ctx: ModelContext) -> None:
    """§3 objective: energy delivered at each market's price, less energy bought.

    ``ctx.cycle_value`` is what one equivalent full cycle is worth, in £,
    charged here so that a window solved in isolation still weighs cycle life
    against the spread in front of it. It is zero in the undecomposed model.
    """
    var = ctx.var
    dt = ctx.params.dt
    cycles_this_window = var.n_cyc[-1] - ctx.state.cycles

    problem += (
        pulp.lpSum(
            dt
            * (
                ctx.settlement.price_1[t] * (ctx.delivered * var.d1[t] - var.c1[t])
                + ctx.settlement.price_2[t] * (ctx.delivered * var.d2[t] - var.c2[t])
            )
            for t in ctx.periods
        )
        - ctx.cycle_value * cycles_this_window
    )


def energy_balance(problem: pulp.LpProblem, ctx: ModelContext) -> None:
    """§4.2 energy balance. Charging is lossy into the store; discharging debits
    the full d, the discharge loss being taken in the objective."""
    var = ctx.var
    for t in ctx.periods:
        problem += (
            var.storage[t]
            == ctx.previous_storage(t)
            + ctx.params.dt * (ctx.retained * (var.c1[t] + var.c2[t]) - var.d1[t] - var.d2[t]),
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


def volume_limit(problem: pulp.LpProblem, ctx: ModelContext) -> None:
    """§4.1 with §4.7 substituted in: S(t) <= S_max(t) = volume (1 - rho n(t))."""
    volume = ctx.params.nominal_volume_mwh
    for t in ctx.periods:
        problem += (
            ctx.var.storage[t] + volume * ctx.params.degradation_per_cycle * ctx.var.n_cyc[t]
            <= volume,
            f"storage_bound_{t}",
        )


def mode_exclusivity(problem: pulp.LpProblem, ctx: ModelContext) -> None:
    """§4.3 charge or discharge, not both, and the rate limits with it.

    The write-up states §4.3 as one pair of inequalities, the rate limit and the
    binary coupling together, and this block is that pair. Omitting it therefore
    removes the aggregate rate caps as well — each market's variable keeps only
    its own bound, so ``c1 + c2`` may reach twice the rate. That is what
    dropping §4.3 means; it is not a relaxation of the binary alone.
    """
    var = ctx.var
    for t in ctx.periods:
        problem += (
            var.c1[t] + var.c2[t] <= ctx.params.max_charge_mw * var.is_charging[t],
            f"charge_rate_{t}",
        )
        problem += (
            var.d1[t] + var.d2[t] <= ctx.params.max_discharge_mw * (1 - var.is_charging[t]),
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

    This row is the *only* thing imposing the budget. Bounding every
    ``n_cyc(t)`` by ``cycle_budget`` would describe the same feasible set — the
    count is non-decreasing, so capping the last period caps them all — but
    :meth:`DispatchVariables.declare` deliberately leaves ``n_cyc`` free of an
    upper bound, so that dropping this block really relaxes the budget rather
    than leaving a variable bound to enforce it. See
    :data:`UNCAPPED_BLOCKS` and the Lagrangian relaxation of §6.
    """
    problem += ctx.var.n_cyc[-1] <= ctx.params.cycle_budget, "cycle_life"


#: The constraints of §4, in the order the write-up states them.
DEFAULT_BLOCKS: tuple[ConstraintBlock, ...] = (
    energy_balance,  # §4.2
    cycle_accounting,  # §4.6
    volume_limit,  # §4.1 + §4.7
    mode_exclusivity,  # §4.3
    hourly_commitment,  # §4.5
    cycle_life_cap,  # §4.6
)


def relaxing(*blocks: ConstraintBlock) -> tuple[ConstraintBlock, ...]:
    """:data:`DEFAULT_BLOCKS` without ``blocks`` — the model that prices them.

    Removing a constraint is how it is valued: solve without it, charge the
    objective for violating it, and the charge that restores feasibility is the
    constraint's shadow price. Raises if a block is not in the default set,
    so a typo cannot silently relax nothing.
    """
    unknown = [block.__name__ for block in blocks if block not in DEFAULT_BLOCKS]
    if unknown:
        raise ValueError(f"not constraints of the default model: {', '.join(unknown)}")
    return tuple(block for block in DEFAULT_BLOCKS if block not in blocks)


#: §4 with the cycle budget removed, for the Lagrangian relaxation of §6.
UNCAPPED_BLOCKS: tuple[ConstraintBlock, ...] = relaxing(cycle_life_cap)
