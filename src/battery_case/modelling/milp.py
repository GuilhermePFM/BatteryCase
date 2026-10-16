"""The mixed-integer linear program of §3 to §4.7, over one window of the grid.

One window is one call to the solver. The horizon is covered by solving a
sequence of windows that hand their end state to the next
(:mod:`battery_case.modelling.rolling`); the formulation here is the same
whether the window is a day or the whole horizon.

Variable and constraint names follow the write-up, so each constraint block can
be read against its section.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
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
    solver: pulp.LpSolver | None = None,
) -> WindowSolution:
    """Maximise profit over ``grid``, starting from ``state``.

    ``cycle_price`` is a charge in £ per equivalent full cycle used, added to
    the objective so that a window solved in isolation still weighs cycle life
    against the spread in front of it. It is zero in the undecomposed model;
    :func:`battery_case.modelling.rolling.calibrate_cycle_price` sets it when
    the cycle budget binds.
    """
    problem, variables = build_problem(grid, params, state, cycle_price=cycle_price)
    stats = problem.solve(solver if solver is not None else default_solver())

    if stats.status is not pulp.LpSolveStatus.Optimal:
        raise RuntimeError(f"Window starting {grid.timestamps[0]} solved as {stats.status.name}")

    return WindowSolution(
        charge_1_mw=_values(variables["c1"]),
        charge_2_mw=_values(variables["c2"]),
        discharge_1_mw=_values(variables["d1"]),
        discharge_2_mw=_values(variables["d2"]),
        storage_mwh=_values(variables["S"]),
        cycles=_values(variables["n_cyc"]),
        status=stats.status.name,
    )


def build_problem(
    grid: DispatchGrid,
    params: ModelParameters,
    state: BatteryState = EMPTY_BATTERY,
    *,
    cycle_price: float = 0.0,
) -> tuple[pulp.LpProblem, dict[str, list[pulp.LpVariable]]]:
    """Assemble the MILP for one window without solving it."""
    periods = range(len(grid))
    dt = params.dt
    keep_charged = 1.0 - params.charge_loss
    delivered = 1.0 - params.discharge_loss
    volume = params.nominal_volume_mwh

    problem = pulp.LpProblem("battery_dispatch", pulp.LpMaximize)

    # Decision variables of §2. The effective volume S_max(t) is substituted out
    # rather than carried as a variable, as §4.7 permits.
    c1 = problem.add_variable_matrix("c1", periods, 0, params.max_charge_mw)
    c2 = problem.add_variable_matrix("c2", periods, 0, params.max_charge_mw)
    d1 = problem.add_variable_matrix("d1", periods, 0, params.max_discharge_mw)
    d2 = problem.add_variable_matrix("d2", periods, 0, params.max_discharge_mw)
    storage = problem.add_variable_matrix("S", periods, 0, volume)
    n_cyc = problem.add_variable_matrix("n_cyc", periods, 0, params.cycle_budget)
    charging = problem.add_variable_matrix("u", periods, cat="Binary")

    cycles_used = n_cyc[-1] - state.cycles

    # §3 objective: energy delivered at each market's price, less energy bought.
    problem += (
        pulp.lpSum(
            dt
            * (
                grid.price_1[t] * (delivered * d1[t] - c1[t])
                + grid.price_2[t] * (delivered * d2[t] - c2[t])
            )
            for t in periods
        )
        - cycle_price * cycles_used
    )

    for t in periods:
        previous_storage = storage[t - 1] if t else state.storage_mwh
        previous_cycles = n_cyc[t - 1] if t else state.cycles

        # §4.2 energy balance. Charging is lossy into the store; discharging
        # debits the full d, the discharge loss being taken in the objective.
        problem += (
            storage[t] == previous_storage + dt * (keep_charged * (c1[t] + c2[t]) - d1[t] - d2[t]),
            f"balance_{t}",
        )

        # §4.6 equivalent full cycles, counted on the discharge side only.
        problem += (
            n_cyc[t] == previous_cycles + dt * (d1[t] + d2[t]) / volume,
            f"cycles_{t}",
        )

        # §4.1 with §4.7 substituted in: S(t) <= S_max(t) = volume (1 - rho n(t)).
        problem += (
            storage[t] + volume * params.degradation_per_cycle * n_cyc[t] <= volume,
            f"storage_bound_{t}",
        )

        # §4.3 charge or discharge, not both, and the rate limits with it.
        problem += c1[t] + c2[t] <= params.max_charge_mw * charging[t], f"charge_rate_{t}"
        problem += (
            d1[t] + d2[t] <= params.max_discharge_mw * (1 - charging[t]),
            f"discharge_rate_{t}",
        )

        # §4.5 Market 2 is committed for its whole hourly interval.
        if t % PERIODS_PER_HOUR:
            problem += c2[t] - c2[t - 1] == 0, f"hourly_charge_{t}"
            problem += d2[t] - d2[t - 1] == 0, f"hourly_discharge_{t}"

    # §4.6 cycle life. The cap is already the upper bound of every n_cyc(t)
    # variable above, which is the same constraint: n_cyc is non-decreasing, so
    # the two forms are equivalent while the budget is one number for the whole
    # horizon. This row is redundant, and kept so a solver log naming it points
    # at the section.
    problem += n_cyc[-1] <= params.cycle_budget, "cycle_life"

    # §4.4 is implied by §4.1 and §4.2 together and is not restated.

    variables = {"c1": c1, "c2": c2, "d1": d1, "d2": d2, "S": storage, "n_cyc": n_cyc}
    return problem, variables


def default_solver(*, time_limit: float | None = None) -> pulp.LpSolver:
    """HiGHS, quietly. It ships as a dependency and reads the model in process."""
    return pulp.HiGHS(msg=False, timeLimit=time_limit)


def _values(variables: list[pulp.LpVariable]) -> np.ndarray:
    return np.array([pulp.value(variable) for variable in variables], dtype=float)
