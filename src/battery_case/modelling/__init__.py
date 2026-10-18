"""Modelling: the dispatch problem of ``docs/model/model.md``.

The formulation lives in :mod:`~battery_case.modelling.constraints` (§3 to
§4.7), is assembled and solved one window at a time by
:mod:`~battery_case.modelling.window_problem`, and is applied to the horizon by
:mod:`~battery_case.modelling.rolling_horizon` (§6); the output it produces is
described by :mod:`~battery_case.modelling.plan`. The cycle budget's value, when
it binds, is found by one of the methods in
:mod:`~battery_case.modelling.dual_search` and dispatched at by
:mod:`~battery_case.modelling.calibrated_policy`.
"""

from battery_case.modelling.calibrated_policy import CalibratedPolicy
from battery_case.modelling.constraints import BatteryState
from battery_case.modelling.dual_problem import CycleOracle, DualBound, DualSearch, DualSearchResult
from battery_case.modelling.dual_search import (
    DEFAULT_SEARCH,
    SEARCHES,
    calibrate_cycle_value,
    search_named,
)
from battery_case.modelling.parameters import ModelParameters, prorated_cycle_budget
from battery_case.modelling.periods import SettlementPeriods, build_periods
from battery_case.modelling.plan import build_plan, summarise
from battery_case.modelling.policy import DispatchPolicy
from battery_case.modelling.rolling_horizon import RollingPolicy
from battery_case.modelling.window_problem import WindowSolution, solve_window

__all__ = [
    "DEFAULT_SEARCH",
    "SEARCHES",
    "BatteryState",
    "CalibratedPolicy",
    "CycleOracle",
    "DispatchPolicy",
    "DualBound",
    "DualSearch",
    "DualSearchResult",
    "ModelParameters",
    "RollingPolicy",
    "SettlementPeriods",
    "WindowSolution",
    "build_periods",
    "build_plan",
    "calibrate_cycle_value",
    "prorated_cycle_budget",
    "search_named",
    "solve_window",
    "summarise",
]
