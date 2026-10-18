"""Finding the cycle value by bisection (§6) — the method the project started with.

The budget cannot be overspent while every window caps the cumulative count, so
the symptom of a binding budget is that it is *used up*, by whichever days come
first rather than by the widest spreads in the horizon. The cycle value that
fixes that is the highest one at which the horizon still spends its whole
budget: below it the early days overbuy, above it cycles are left unused that
would have paid for themselves.

Cycle use falls monotonically in the cycle value, so the value is bisected. The
signal each pass gives up is one bit — *was the budget exhausted?* — which is
all a capped pass can report, and all this method needs.

What it cannot do is say how good the answer is. The bit carries no slope, so
there is no dual bound to be had here, and :attr:`DualSearchResult.bound` is
``None``. :mod:`battery_case.modelling.cycle_value.cutting_plane` is the method that trades
the bit for a Lagrangian and a subgradient and gets a certificate back.
"""

from __future__ import annotations

from dataclasses import dataclass

from battery_case.modelling.cycle_value.oracle import (
    SPENT_TOLERANCE,
    CycleOracle,
    DualPoint,
    DualSearchResult,
)


@dataclass(frozen=True, slots=True)
class BisectionSearch:
    """Bisect the cycle value between zero and ``upper_bound``. Implements ``DualSearch``.

    ``tolerance`` is the fraction of the budget that may go unspent while the
    budget still counts as fully used. The cost is fixed at ``1 +
    max_iterations`` passes whatever the instance: one probe to find out whether
    the budget binds at all, then a halving each pass.
    """

    upper_bound: float = 200.0
    tolerance: float = SPENT_TOLERANCE
    max_iterations: int = 12

    def search(self, oracle: CycleOracle) -> DualSearchResult:
        """Find the cycle value, on capped passes, and return the plan with it."""
        spent_in_full = oracle.budget * (1.0 - self.tolerance)

        best = oracle.at(0.0, relaxed=False)
        if best.cycles < spent_in_full:
            # The budget is not binding: no rationing is needed, and the
            # uncharged plan is already the answer.
            return _result(0.0, best, oracle)

        low, high = 0.0, self.upper_bound
        best_cycle_value = 0.0
        for _ in range(self.max_iterations):
            cycle_value = 0.5 * (low + high)
            point = oracle.at(cycle_value, relaxed=False)
            if point.cycles >= spent_in_full:
                low, best_cycle_value, best = cycle_value, cycle_value, point
            else:
                high = cycle_value

        return _result(best_cycle_value, best, oracle)


def _result(cycle_value: float, point: DualPoint, oracle: CycleOracle) -> DualSearchResult:
    return DualSearchResult(
        cycle_value=cycle_value,
        plan=point.plan,
        profit=point.profit,
        cycles=point.cycles,
        passes=oracle.passes,
        bound=None,
    )
