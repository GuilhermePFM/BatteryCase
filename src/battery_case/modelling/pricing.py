"""The seam between pricing the cycle budget and the method that prices it (§6).

The cycle budget of §4.6 is the one constraint that couples distant windows, and
it is handled by pricing rather than splitting: a charge ``λ`` per equivalent
full cycle enters each window's objective, and the charge that rations the
budget across the horizon is its shadow price. *Finding* that charge is a search
over a scalar, and there is more than one way to run it, so the search is a
strategy (:class:`CyclePricer`) rather than a function.

What every method shares is the expensive part. One evaluation is one pass of
the rolling dispatcher over the whole horizon — about 77 seconds on this data —
and a method is judged by how many passes it spends. :class:`CycleOracle` owns
that primitive, memoises it, and counts the passes it serves, so the count is
measured in one place rather than asserted by each method.

What the methods do *not* share is the subproblem. A method that reads a
subgradient needs the cap removed and replaced by the charge
(:data:`~battery_case.modelling.constraints.RELAXED_BLOCKS`), because a window
that still caps the count reports the same clipped number at every λ and so no
usable slope; a method that reads only "was the budget exhausted" needs the cap
in place. The ``relaxed`` flag on :meth:`CycleOracle.at` is therefore the
method's own choice, which is why a pricer is a search rule *and* a relaxation.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Protocol

import pandas as pd

from battery_case.modelling.constraints import DEFAULT_BLOCKS, RELAXED_BLOCKS
from battery_case.modelling.grid import DispatchGrid
from battery_case.modelling.parameters import ModelParameters
from battery_case.modelling.rolling import RollingDispatcher

#: Fraction of the budget that may go unspent while it still counts as used up.
SPENT_IN_FULL = 1e-3


@dataclass(frozen=True, slots=True)
class DualPoint:
    """One pass at one charge: everything either method could read from it.

    ``value`` is the Lagrangian ``L(λ)`` of §6 and ``subgradient`` is its exact
    subgradient *provided the pass maximised the relaxed problem* — which a
    rolling pass with finite lookahead only approximates, and which is why a
    bound quoted from these points is sound only as far as that approximation
    holds. A point taken from a capped pass carries a subgradient that is zero
    wherever the cap binds, and is no use to a method that differentiates.
    """

    price: float
    value: float
    subgradient: float
    profit: float
    cycles: float
    schedule: pd.DataFrame
    relaxed: bool
    feasible: bool

    @property
    def cut(self) -> tuple[float, float, float]:
        """The cut ``L(λ) >= value + subgradient (λ - price)`` of §6."""
        return self.price, self.value, self.subgradient


@dataclass(frozen=True, slots=True)
class DualBound:
    """An upper bound on the constrained optimum, with the gap that earns it.

    ``value`` is the best ``L(λ)`` evaluated, an upper bound on the optimum by
    weak duality; ``master_value`` is the cuts' envelope minimum, a lower bound
    on the dual optimum. The two bracket ``min_λ L(λ)``, and the gap between
    them is what the search terminates on.
    """

    value: float
    master_value: float

    @property
    def gap(self) -> float:
        return self.value - self.master_value

    @property
    def relative_gap(self) -> float:
        return self.gap / abs(self.value) if self.value else 0.0


@dataclass(frozen=True, slots=True)
class PricingResult:
    """What a pricer returns: a charge, a deliverable schedule, and its cost.

    ``bound`` is ``None`` when the method has nothing to certify with — the
    absence of a certificate is a type here rather than a sentinel number, so a
    report cannot quote a bound a method never computed.
    """

    price: float
    schedule: pd.DataFrame
    profit: float
    cycles: float
    passes: int
    bound: DualBound | None = None


@dataclass(frozen=True, slots=True)
class CycleOracle:
    """One rolling pass at one charge, memoised and counted.

    The dispatcher is the window scheme of §6; the oracle only ever varies its
    charge and its constraints, which is why both are fields of a frozen
    dataclass and a pass is a :func:`~dataclasses.replace` away.
    """

    grid: DispatchGrid
    params: ModelParameters
    dispatcher: RollingDispatcher = field(default_factory=RollingDispatcher)
    _points: list[DualPoint] = field(default_factory=list, repr=False, compare=False)
    _cache: dict[tuple[float, bool], DualPoint] = field(
        default_factory=dict, repr=False, compare=False
    )

    @property
    def budget(self) -> float:
        """The cycle budget being priced, ``B`` in the dual of §6."""
        return self.params.cycle_budget

    @property
    def passes(self) -> int:
        """Passes solved so far — the cost of the search, in ten-minute units."""
        return len(self._points)

    @property
    def points(self) -> tuple[DualPoint, ...]:
        """Every pass solved, in the order it was asked for."""
        return tuple(self._points)

    def at(self, price: float, *, relaxed: bool) -> DualPoint:
        """Dispatch the horizon charged ``price`` per cycle, and read the pass.

        ``relaxed`` drops the cycle budget from the model, leaving the charge as
        the only thing standing between the battery and spending every cycle it
        can. A capped pass keeps the budget, so its schedule is deliverable as
        it stands and its subgradient is uninformative.
        """
        key = (price, relaxed)
        if key not in self._cache:
            self._cache[key] = self._solve(price, relaxed=relaxed)
            self._points.append(self._cache[key])
        return self._cache[key]

    def _solve(self, price: float, *, relaxed: bool) -> DualPoint:
        dispatcher = replace(
            self.dispatcher,
            cycle_price=price,
            blocks=RELAXED_BLOCKS if relaxed else DEFAULT_BLOCKS,
        )
        schedule = dispatcher.run_on_grid(self.grid, self.params)

        profit = float(schedule["revenue_gbp"].sum())
        cycles = float(schedule["cycles"].iloc[-1])
        return DualPoint(
            price=price,
            value=profit - price * (cycles - self.budget),
            subgradient=self.budget - cycles,
            profit=profit,
            cycles=cycles,
            schedule=schedule,
            relaxed=relaxed,
            feasible=cycles <= self.budget * (1.0 + SPENT_IN_FULL),
        )


class CyclePricer(Protocol):
    """A way of finding the charge per cycle that rations the budget (§6)."""

    def price(self, oracle: CycleOracle) -> PricingResult:
        """Search for the charge, spending oracle passes, and return a schedule.

        The schedule returned must respect the budget: a relaxed pass is an
        evaluation, not a deliverable.
        """
        ...
