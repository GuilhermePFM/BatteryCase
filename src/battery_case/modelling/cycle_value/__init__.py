"""The outer search for the cycle budget's value (§6 of ``docs/model/model.md``).

Everything here sits downstream of the formulation: the modules in the parent
package assemble and solve the dispatch problem at a *given* cycle value, and
these find the value itself. :mod:`~battery_case.modelling.cycle_value.oracle`
is the seam -- one pass of the horizon at one candidate value -- which
:mod:`~battery_case.modelling.cycle_value.bisection` and
:mod:`~battery_case.modelling.cycle_value.cutting_plane` then search in two
different ways. :mod:`~battery_case.modelling.cycle_value.searches` is the
registry that names them and
:mod:`~battery_case.modelling.cycle_value.calibrated_policy` runs one end to
end as a :class:`~battery_case.modelling.policy.DispatchPolicy`.

The dependency runs one way: nothing in the parent package imports from here.
"""

from battery_case.modelling.cycle_value.bisection import BisectionSearch
from battery_case.modelling.cycle_value.calibrated_policy import CalibratedPolicy
from battery_case.modelling.cycle_value.cutting_plane import CuttingPlaneSearch
from battery_case.modelling.cycle_value.oracle import (
    CycleOracle,
    DualBound,
    DualPoint,
    DualSearch,
    DualSearchResult,
)
from battery_case.modelling.cycle_value.searches import (
    DEFAULT_SEARCH,
    SEARCHES,
    calibrate_cycle_value,
    search_named,
)

__all__ = [
    "DEFAULT_SEARCH",
    "SEARCHES",
    "BisectionSearch",
    "CalibratedPolicy",
    "CuttingPlaneSearch",
    "CycleOracle",
    "DualBound",
    "DualPoint",
    "DualSearch",
    "DualSearchResult",
    "calibrate_cycle_value",
    "search_named",
]
