"""Covering the horizon with a sequence of MILP windows (§6).

Solving all 52,608 periods in one mixed-integer program is not practical: the
binary of §4.3 appears in every period, and solve time grows sharply with the
window length. The horizon is therefore walked in windows that each commit one
day and look one day further ahead, carrying the state of charge and the cycle
count forward (:class:`~battery_case.modelling.constraints.BatteryState`). The
lookahead is solved and then discarded; it exists so the committed day is not
decided as if the horizon ended at midnight.

Two couplings reach beyond a single window:

* the **state of charge**, which the handover carries exactly;
* the **cycle budget** of §4.6, which is global. Each window carries the cycles
  already spent and caps the total, so the budget can never be overspent — but
  a window cannot see what a later one would have done with a cycle, so a
  binding budget is simply exhausted by the earliest days. The budget is
  therefore *priced*: ``cycle_price`` charges the objective per equivalent full
  cycle used, which makes each window spend cycles only on spreads worth that
  charge, and :func:`calibrate_cycle_price` finds the charge that rations the
  budget across the horizon. With the full 5,000-cycle budget of §5 the cap is
  not reached on this price data and the charge stays at zero; it earns its
  keep under the pro-rated budget, or on a longer horizon.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from battery_case.data_models import BatterySpec, MarketPrices
from battery_case.modelling.constraints import EMPTY_BATTERY
from battery_case.modelling.grid import PERIODS_PER_HOUR, DispatchGrid, build_grid
from battery_case.modelling.milp import default_solver, solve_window
from battery_case.modelling.parameters import ModelParameters
from battery_case.modelling.schedule import build_schedule

#: Periods in a day — the default window and lookahead length.
PERIODS_PER_DAY = 48

_DECISIONS = (
    "charge_1_mw",
    "charge_2_mw",
    "discharge_1_mw",
    "discharge_2_mw",
    "storage_mwh",
    "cycles",
)


@dataclass(frozen=True, slots=True)
class RollingDispatcher:
    """Dispatch by rolling MILP windows. Implements ``Dispatcher``.

    ``commit_periods`` is how much of each window is kept, ``lookahead_periods``
    how far past it the window sees. Both must be whole hours, so that the
    hourly commitment of §4.5 is never split across a window boundary.
    """

    commit_periods: int = PERIODS_PER_DAY
    lookahead_periods: int = PERIODS_PER_DAY
    cycle_price: float = 0.0
    time_limit: float | None = None
    on_window: Callable[[int, int], None] | None = None

    def __post_init__(self) -> None:
        if self.commit_periods < 1:
            raise ValueError("commit_periods must be at least one period")
        if self.lookahead_periods < 0:
            raise ValueError("lookahead_periods cannot be negative")
        for name in ("commit_periods", "lookahead_periods"):
            if getattr(self, name) % PERIODS_PER_HOUR:
                raise ValueError(f"{name} must be a whole number of hours")

    def run(self, spec: BatterySpec, prices: MarketPrices) -> pd.DataFrame:
        """Dispatch against both price series, from the raw inputs."""
        return self.run_on_grid(build_grid(prices), ModelParameters.from_spec(spec))

    def run_on_grid(self, grid: DispatchGrid, params: ModelParameters) -> pd.DataFrame:
        """Dispatch over a prepared grid, returning the schedule."""
        solver = default_solver(time_limit=self.time_limit)
        parts: dict[str, list[np.ndarray]] = {name: [] for name in _DECISIONS}
        state = EMPTY_BATTERY

        for start in range(0, len(grid), self.commit_periods):
            window = grid.window(start, self.commit_periods + self.lookahead_periods)
            solution = solve_window(
                window, params, state, cycle_price=self.cycle_price, solver=solver
            )
            committed = min(self.commit_periods, len(window))
            for name in _DECISIONS:
                parts[name].append(getattr(solution, name)[:committed])
            state = solution.state_after(committed)
            if self.on_window is not None:
                self.on_window(start + committed, len(grid))

        decisions = {name: np.concatenate(values) for name, values in parts.items()}
        return build_schedule(grid, params, **decisions)


def calibrate_cycle_price(
    grid: DispatchGrid,
    params: ModelParameters,
    *,
    dispatcher: RollingDispatcher | None = None,
    upper_bound: float = 200.0,
    tolerance: float = 1e-3,
    max_iterations: int = 12,
) -> tuple[float, pd.DataFrame]:
    """Find the charge per cycle that rations a binding cycle budget.

    The budget cannot be overspent — every window caps the cumulative count —
    so the symptom of a binding budget is that it is *used up*, by whichever
    days come first rather than by the widest spreads in the horizon. The charge
    that fixes that is the budget's shadow price: the highest charge at which
    the horizon still spends its whole budget. Below it the early days overbuy;
    above it cycles are left unused that would have paid for themselves.

    Cycle use falls monotonically in the charge, so the charge is bisected
    between zero and ``upper_bound``. A budget that is not exhausted at zero is
    not binding, and zero is returned after a single run. The schedule comes
    back with the charge, so no run is wasted.

    ``tolerance`` is the fraction of the budget that may go unspent while the
    budget still counts as fully used.
    """
    dispatcher = dispatcher if dispatcher is not None else RollingDispatcher()
    spent_in_full = params.cycle_budget * (1.0 - tolerance)

    best_price = 0.0
    best_schedule = replace(dispatcher, cycle_price=0.0).run_on_grid(grid, params)
    if _cycles_used(best_schedule) < spent_in_full:
        return best_price, best_schedule

    low, high = 0.0, upper_bound
    for _ in range(max_iterations):
        price = 0.5 * (low + high)
        schedule = replace(dispatcher, cycle_price=price).run_on_grid(grid, params)
        if _cycles_used(schedule) >= spent_in_full:
            low, best_price, best_schedule = price, price, schedule
        else:
            high = price

    return best_price, best_schedule


def _cycles_used(schedule: pd.DataFrame) -> float:
    return float(schedule["cycles"].iloc[-1])
