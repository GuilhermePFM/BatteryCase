"""Pricing the cycle budget by bisection (§6) — the method the project started with.

The budget cannot be overspent while every window caps the cumulative count, so
the symptom of a binding budget is that it is *used up*, by whichever days come
first rather than by the widest spreads in the horizon. The charge that fixes
that is the highest one at which the horizon still spends its whole budget:
below it the early days overbuy, above it cycles are left unused that would have
paid for themselves.

Cycle use falls monotonically in the charge, so the charge is bisected. The
signal each pass gives up is one bit — *was the budget exhausted?* — which is
all a capped pass can report, and all this method needs.

What it cannot do is say how good the answer is. The bit carries no slope, so
there is no dual bound to be had here, and :attr:`PricingResult.bound` is
``None``. :mod:`battery_case.modelling.cutting_plane` is the method that trades
the bit for a value and a subgradient and gets a certificate back.
"""

from __future__ import annotations

from dataclasses import dataclass

from battery_case.modelling.pricing import (
    SPENT_IN_FULL,
    CycleOracle,
    DualPoint,
    PricingResult,
)


@dataclass(frozen=True, slots=True)
class BisectionPricer:
    """Bisect the charge between zero and ``upper_bound``. Implements ``CyclePricer``.

    ``tolerance`` is the fraction of the budget that may go unspent while the
    budget still counts as fully used. The cost is fixed at ``1 +
    max_iterations`` passes whatever the instance: one probe to find out whether
    the budget binds at all, then a halving each pass.
    """

    upper_bound: float = 200.0
    tolerance: float = SPENT_IN_FULL
    max_iterations: int = 12

    def price(self, oracle: CycleOracle) -> PricingResult:
        """Find the charge, on capped passes, and return the schedule with it."""
        spent_in_full = oracle.budget * (1.0 - self.tolerance)

        best = oracle.at(0.0, relaxed=False)
        if best.cycles < spent_in_full:
            # The budget is not binding: no rationing is needed, and the
            # unpriced schedule is already the answer.
            return _result(0.0, best, oracle)

        low, high = 0.0, self.upper_bound
        best_price = 0.0
        for _ in range(self.max_iterations):
            price = 0.5 * (low + high)
            point = oracle.at(price, relaxed=False)
            if point.cycles >= spent_in_full:
                low, best_price, best = price, price, point
            else:
                high = price

        return _result(best_price, best, oracle)


def _result(price: float, point: DualPoint, oracle: CycleOracle) -> PricingResult:
    return PricingResult(
        price=price,
        schedule=point.schedule,
        profit=point.profit,
        cycles=point.cycles,
        passes=oracle.passes,
        bound=None,
    )
