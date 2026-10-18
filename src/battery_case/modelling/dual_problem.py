"""The seam between valuing a cycle and the method that finds the value (§6).

The cycle budget of §4.6 is the one constraint that couples distant windows, and
it is handled by valuing rather than splitting: a cycle value ``λ`` per
equivalent full cycle enters each window's objective, and the value that rations
the budget across the horizon is its shadow price. *Finding* that value is a
search over a scalar, and there is more than one way to run it, so the search is
a strategy (:class:`DualSearch`) rather than a function.

What every method shares is the expensive part. One evaluation is one pass of
the rolling policy over the whole horizon — about 77 seconds on this data —
and a method is judged by how many passes it spends. :class:`CycleOracle` owns
that primitive, memoises it, and counts the passes it serves, so the count is
measured in one place rather than asserted by each method.

What the methods do *not* share is the subproblem. A method that reads a
subgradient needs the cap removed and replaced by the cycle value
(:data:`~battery_case.modelling.constraints.UNCAPPED_BLOCKS`), because a window
that still caps the count reports the same clipped number at every λ and so no
usable slope; a method that reads only "was the budget exhausted" needs the cap
in place. The ``relaxed`` flag on :meth:`CycleOracle.at` is therefore the
method's own choice, which is why a search is a search rule *and* a relaxation.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Protocol

import pandas as pd

from battery_case.modelling.constraints import DEFAULT_BLOCKS, UNCAPPED_BLOCKS
from battery_case.modelling.parameters import ModelParameters
from battery_case.modelling.periods import SettlementPeriods
from battery_case.modelling.rolling_horizon import RollingPolicy

#: Fraction of the budget that may go unspent while it still counts as used up.
SPENT_TOLERANCE = 1e-3


@dataclass(frozen=True, slots=True)
class DualPoint:
    """One pass at one cycle value: everything either method could read from it.

    ``lagrangian`` is ``L(λ)`` of §6 and ``subgradient`` is its exact
    subgradient *provided the pass maximised the relaxed problem* — which a
    rolling pass with finite lookahead only approximates, and which is why a
    bound quoted from these points is sound only as far as that approximation
    holds. A point taken from a capped pass carries a subgradient that is zero
    wherever the cap binds, and is no use to a method that differentiates.
    """

    cycle_value: float
    lagrangian: float
    subgradient: float
    profit: float
    cycles: float
    plan: pd.DataFrame
    relaxed: bool
    within_budget: bool

    @property
    def cut(self) -> tuple[float, float, float]:
        """The cut ``L(λ) >= lagrangian + subgradient (λ - cycle_value)`` of §6."""
        return self.cycle_value, self.lagrangian, self.subgradient


@dataclass(frozen=True, slots=True)
class DualBound:
    """An upper bound on the constrained optimum, with the gap that earns it.

    ``lagrangian`` is the best ``L(λ)`` evaluated, an upper bound on the optimum
    by weak duality; ``envelope`` is the cuts' envelope minimum, a lower bound
    on the dual optimum. The two bracket ``min_λ L(λ)``, and the gap between
    them is what the search terminates on.
    """

    lagrangian: float
    envelope: float

    @property
    def gap(self) -> float:
        return self.lagrangian - self.envelope

    @property
    def relative_gap(self) -> float:
        return self.gap / abs(self.lagrangian) if self.lagrangian else 0.0


@dataclass(frozen=True, slots=True)
class DualSearchResult:
    """What a search returns: a cycle value, a deliverable plan, and its cost.

    ``bound`` is ``None`` when the method has nothing to certify with — the
    absence of a certificate is a type here rather than a sentinel number, so a
    report cannot quote a bound a method never computed.
    """

    cycle_value: float
    plan: pd.DataFrame
    profit: float
    cycles: float
    passes: int
    bound: DualBound | None = None


@dataclass(frozen=True, slots=True)
class CycleOracle:
    """One rolling pass at one cycle value, memoised and counted.

    The policy is the window scheme of §6; the oracle only ever varies the
    cycle value and the constraints, which is why both are fields of a frozen
    dataclass and a pass is a :func:`~dataclasses.replace` away.
    """

    settlement: SettlementPeriods
    params: ModelParameters
    policy: RollingPolicy = field(default_factory=RollingPolicy)
    _points: list[DualPoint] = field(default_factory=list, repr=False, compare=False)
    _cache: dict[tuple[float, bool], DualPoint] = field(
        default_factory=dict, repr=False, compare=False
    )

    @property
    def budget(self) -> float:
        """The cycle budget being valued, ``B`` in the dual of §6."""
        return self.params.cycle_budget

    @property
    def passes(self) -> int:
        """Passes solved so far — the cost of the search, in ten-minute units."""
        return len(self._points)

    @property
    def points(self) -> tuple[DualPoint, ...]:
        """Every pass solved, in the order it was asked for."""
        return tuple(self._points)

    def at(self, cycle_value: float, *, relaxed: bool) -> DualPoint:
        """Dispatch the horizon charged ``cycle_value`` per cycle, and read the pass.

        ``relaxed`` drops the cycle budget from the model, leaving the cycle
        value as the only thing standing between the battery and spending every
        cycle it can. A capped pass keeps the budget, so its plan is deliverable
        as it stands and its subgradient is uninformative.
        """
        key = (cycle_value, relaxed)
        if key not in self._cache:
            self._cache[key] = self._solve(cycle_value, relaxed=relaxed)
            self._points.append(self._cache[key])
        return self._cache[key]

    def _solve(self, cycle_value: float, *, relaxed: bool) -> DualPoint:
        policy = replace(
            self.policy,
            cycle_value=cycle_value,
            blocks=UNCAPPED_BLOCKS if relaxed else DEFAULT_BLOCKS,
        )
        plan = policy.dispatch(self.settlement, self.params)

        profit = float(plan["net_revenue_gbp"].sum())
        cycles = float(plan["cycles"].iloc[-1])
        return DualPoint(
            cycle_value=cycle_value,
            lagrangian=profit - cycle_value * (cycles - self.budget),
            subgradient=self.budget - cycles,
            profit=profit,
            cycles=cycles,
            plan=plan,
            relaxed=relaxed,
            within_budget=cycles <= self.budget * (1.0 + SPENT_TOLERANCE),
        )


class DualSearch(Protocol):
    """A way of finding the value per cycle that rations the budget (§6)."""

    def search(self, oracle: CycleOracle) -> DualSearchResult:
        """Search for the cycle value, spending oracle passes, and return a plan.

        The plan returned must respect the budget: a relaxed pass is an
        evaluation, not a deliverable.
        """
        ...
