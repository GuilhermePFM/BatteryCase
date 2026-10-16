"""Modelling: the dispatch problem of ``docs/model/model.md``.

The formulation lives in :mod:`~battery_case.modelling.constraints` (§3 to
§4.7), is assembled and solved one window at a time by
:mod:`~battery_case.modelling.milp`, and is applied to the horizon by
:mod:`~battery_case.modelling.rolling` (§6); the output it produces is described
by :mod:`~battery_case.modelling.schedule`.
"""

from battery_case.modelling.constraints import BatteryState
from battery_case.modelling.dispatch import Dispatcher
from battery_case.modelling.grid import DispatchGrid, build_grid
from battery_case.modelling.milp import WindowSolution, solve_window
from battery_case.modelling.parameters import ModelParameters, prorated_cycle_budget
from battery_case.modelling.rolling import RollingDispatcher, calibrate_cycle_price
from battery_case.modelling.schedule import build_schedule, summarise

__all__ = [
    "BatteryState",
    "DispatchGrid",
    "Dispatcher",
    "ModelParameters",
    "RollingDispatcher",
    "WindowSolution",
    "build_grid",
    "build_schedule",
    "calibrate_cycle_price",
    "prorated_cycle_budget",
    "solve_window",
    "summarise",
]
