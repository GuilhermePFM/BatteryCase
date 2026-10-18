"""The decision variables of §2 and the state the formulation carries forward.

:class:`DispatchVariables` declares one list per symbol of §2, and
:class:`ModelContext` bundles them with the data a constraint block reads.
:class:`BatteryState` is what one window hands to the next: the store and the
cycle count at the end of it.

The constraints themselves live in :mod:`battery_case.modelling.constraints`,
which reads this module and is not read by it.
"""

from __future__ import annotations

from dataclasses import dataclass

import pulp

from battery_case.modelling.parameters import ModelParameters
from battery_case.modelling.periods import SettlementPeriods


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
    is_charging: list[pulp.LpVariable]

    @classmethod
    def declare(
        cls, problem: pulp.LpProblem, periods: range, params: ModelParameters
    ) -> DispatchVariables:
        """Add the variables to ``problem``, bounded by the spec (§2, §4.1).

        ``n_cyc`` is left without an upper bound on purpose, so that
        :func:`~battery_case.modelling.constraints.cycle_life_cap` is the only
        place the budget of §4.6 is imposed and omitting that block really
        relaxes it. The cycle count is bounded anyway:
        :func:`~battery_case.modelling.constraints.cycle_accounting` ties it to
        the discharge of each period, which §4.3 rate-limits.
        """
        return cls(
            c1=problem.add_variable_matrix("c1", periods, 0, params.max_charge_mw),
            c2=problem.add_variable_matrix("c2", periods, 0, params.max_charge_mw),
            d1=problem.add_variable_matrix("d1", periods, 0, params.max_discharge_mw),
            d2=problem.add_variable_matrix("d2", periods, 0, params.max_discharge_mw),
            storage=problem.add_variable_matrix("S", periods, 0, params.nominal_volume_mwh),
            n_cyc=problem.add_variable_matrix("n_cyc", periods, 0),
            is_charging=problem.add_variable_matrix("u", periods, cat="Binary"),
        )


@dataclass(frozen=True, slots=True)
class ModelContext:
    """Everything a block reads: the data, the variables, and the state before them.

    The derived quantities of §4.2 are properties here so that each block reads
    like the write-up without recomputing them.
    """

    settlement: SettlementPeriods
    params: ModelParameters
    state: BatteryState
    var: DispatchVariables
    cycle_value: float = 0.0

    @classmethod
    def declare(
        cls,
        problem: pulp.LpProblem,
        settlement: SettlementPeriods,
        params: ModelParameters,
        state: BatteryState = EMPTY_BATTERY,
        *,
        cycle_value: float = 0.0,
    ) -> ModelContext:
        """Declare the variables on ``problem`` and bundle them with the data."""
        periods = range(len(settlement))
        return cls(
            settlement=settlement,
            params=params,
            state=state,
            var=DispatchVariables.declare(problem, periods, params),
            cycle_value=cycle_value,
        )

    @property
    def periods(self) -> range:
        """The period indices of the window."""
        return range(len(self.settlement))

    @property
    def retained(self) -> float:
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
