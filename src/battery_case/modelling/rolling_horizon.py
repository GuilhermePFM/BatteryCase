"""Covering the horizon with a sequence of MILP windows (§6).

Solving all 52,608 periods in one mixed-integer program is not practical: the
binary of §4.3 appears in every period, and solve time grows sharply with the
window length. The horizon is therefore walked in windows that each commit one
day and look one day further ahead, carrying the storage and the cycle count
forward (:class:`~battery_case.modelling.variables.BatteryState`). The
lookahead is solved and then discarded; it exists so the committed day is not
decided as if the horizon ended at midnight.

Two couplings reach beyond a single window:

* the **storage**, which the handover carries exactly;
* the **cycle budget** of §4.6, which is global. Each window carries the cycles
  already spent and caps the total, so the budget can never be overspent — but
  a window cannot see what a later one would have done with a cycle, so a
  binding budget is simply exhausted by the earliest days. The budget is
  therefore *valued*: ``cycle_value`` charges the objective per equivalent full
  cycle used, which makes each window spend cycles only on spreads worth that
  much, and the search for the value that rations the budget across the horizon
  lives in :mod:`battery_case.modelling.cycle_value.oracle` and the two methods beside it.
  With the full 5,000-cycle budget of §5 the cap is not reached on this price
  data and the cycle value stays at zero; it earns its keep under the pro-rated
  budget, or on a longer horizon.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from battery_case.data_models import BatterySpec, MarketPrices
from battery_case.modelling.constraints import DEFAULT_BLOCKS, ConstraintBlock
from battery_case.modelling.parameters import ModelParameters
from battery_case.modelling.periods import PERIODS_PER_HOUR, SettlementPeriods, build_periods
from battery_case.modelling.plan import build_plan
from battery_case.modelling.variables import EMPTY_BATTERY
from battery_case.modelling.window_problem import default_solver, solve_window

#: Periods in a day — the default window and lookahead length.
PERIODS_PER_DAY = 48


@dataclass(frozen=True, slots=True)
class WindowProgress:
    """How far a pass has got, as the window that was just committed.

    The window, not the period, is the unit of work: one window is one MILP
    solve, so a rate quoted in windows per second is the rate that predicts
    what is left. ``at`` is where in the horizon the pass has reached, which
    is the one thing a period count cannot tell a reader.
    """

    window: int
    windows: int
    periods_done: int
    periods: int
    at: pd.Timestamp

    @property
    def fraction(self) -> float:
        return self.window / self.windows if self.windows else 1.0


_DECISIONS = (
    "charge_1_mw",
    "charge_2_mw",
    "discharge_1_mw",
    "discharge_2_mw",
    "storage_mwh",
    "cycles",
)


@dataclass(frozen=True, slots=True)
class RollingPolicy:
    """Dispatch by rolling MILP windows. Implements ``DispatchPolicy``.

    ``commit_periods`` is how much of each window is kept, ``lookahead_periods``
    how far past it the window sees. Both must be whole hours, so that the
    hourly commitment of §4.5 is never split across a window boundary.

    ``blocks`` are the constraints each window imposes. The default is the whole
    of §4; a pass of the Lagrangian relaxation of §6 drops the cycle budget from
    it (:data:`~battery_case.modelling.constraints.UNCAPPED_BLOCKS`) and charges
    ``cycle_value`` for cycles instead. The dataclass is frozen, so a relaxed
    pass is ``replace(policy, blocks=UNCAPPED_BLOCKS, cycle_value=...)`` and
    nothing else in the loop changes.
    """

    commit_periods: int = PERIODS_PER_DAY
    lookahead_periods: int = PERIODS_PER_DAY
    cycle_value: float = 0.0
    blocks: tuple[ConstraintBlock, ...] = DEFAULT_BLOCKS
    time_limit: float | None = None
    on_window: Callable[[WindowProgress], None] | None = None

    def __post_init__(self) -> None:
        if self.commit_periods < 1:
            raise ValueError("commit_periods must be at least one period")
        if self.lookahead_periods < 0:
            raise ValueError("lookahead_periods cannot be negative")
        for name in ("commit_periods", "lookahead_periods"):
            if getattr(self, name) % PERIODS_PER_HOUR:
                raise ValueError(f"{name} must be a whole number of hours")

    def window_count(self, periods: int) -> int:
        """How many windows cover ``periods`` — the pass length, known up front."""
        return math.ceil(periods / self.commit_periods)

    def run(self, spec: BatterySpec, prices: MarketPrices) -> pd.DataFrame:
        """Dispatch against both price series, from the raw inputs."""
        return self.dispatch(build_periods(prices), ModelParameters.from_spec(spec))

    def dispatch(self, settlement: SettlementPeriods, params: ModelParameters) -> pd.DataFrame:
        """Dispatch over a prepared settlement, returning the plan."""
        solver = default_solver(
            time_limit=self.time_limit,
            periods=self.commit_periods + self.lookahead_periods,
        )
        parts: dict[str, list[np.ndarray]] = {name: [] for name in _DECISIONS}
        state = EMPTY_BATTERY

        windows = self.window_count(len(settlement))
        for index, start in enumerate(range(0, len(settlement), self.commit_periods), start=1):
            window = settlement.window(start, self.commit_periods + self.lookahead_periods)
            solution = solve_window(
                window,
                params,
                state,
                cycle_value=self.cycle_value,
                blocks=self.blocks,
                solver=solver,
            )
            committed = min(self.commit_periods, len(window))
            for name in _DECISIONS:
                parts[name].append(getattr(solution, name)[:committed])
            state = solution.state_after(committed)
            if self.on_window is not None:
                self.on_window(
                    WindowProgress(
                        window=index,
                        windows=windows,
                        periods_done=start + committed,
                        periods=len(settlement),
                        at=window.timestamps[0],
                    )
                )

        decisions = {name: np.concatenate(values) for name, values in parts.items()}
        return build_plan(settlement, params, **decisions)
