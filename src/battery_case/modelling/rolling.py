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
  charge, and the search for the charge that rations the budget across the
  horizon lives in :mod:`battery_case.modelling.pricing` and the two methods
  beside it. With the full 5,000-cycle budget of §5 the cap is not reached on
  this price data and the charge stays at zero; it earns its keep under the
  pro-rated budget, or on a longer horizon.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from battery_case.data_models import BatterySpec, MarketPrices
from battery_case.modelling.constraints import DEFAULT_BLOCKS, EMPTY_BATTERY, ConstraintBlock
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

    ``blocks`` are the constraints each window imposes. The default is the whole
    of §4; a pass of the Lagrangian relaxation of §6 drops the cycle budget from
    it (:data:`~battery_case.modelling.constraints.RELAXED_BLOCKS`) and charges
    ``cycle_price`` for cycles instead. The dataclass is frozen, so a relaxed
    pass is ``replace(dispatcher, blocks=RELAXED_BLOCKS, cycle_price=...)`` and
    nothing else in the loop changes.
    """

    commit_periods: int = PERIODS_PER_DAY
    lookahead_periods: int = PERIODS_PER_DAY
    cycle_price: float = 0.0
    blocks: tuple[ConstraintBlock, ...] = DEFAULT_BLOCKS
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
                window,
                params,
                state,
                cycle_price=self.cycle_price,
                blocks=self.blocks,
                solver=solver,
            )
            committed = min(self.commit_periods, len(window))
            for name in _DECISIONS:
                parts[name].append(getattr(solution, name)[:committed])
            state = solution.state_after(committed)
            if self.on_window is not None:
                self.on_window(start + committed, len(grid))

        decisions = {name: np.concatenate(values) for name, values in parts.items()}
        return build_schedule(grid, params, **decisions)
