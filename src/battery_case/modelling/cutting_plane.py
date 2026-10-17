"""Pricing the cycle budget by Kelley's cutting-plane method (§6).

The dual function ``L(λ)`` of §6 is convex and piecewise linear, being a
pointwise maximum of functions affine in ``λ``, and each pass of the *relaxed*
problem hands back both its value and an exact subgradient. So each pass
contributes a **cut**: a linear function lying everywhere below ``L``. The next
charge to try is the minimiser of the cuts' upper envelope — a two-variable
linear program with one row per pass, negligible beside the pass itself.

The method then brackets its own answer. The best ``L(λ)`` evaluated is an upper
bound on ``min_λ L(λ)``, and by weak duality on the constrained optimum as well;
the master's value is a lower bound on the same quantity, the cuts being
underestimators. The loop therefore stops on a measured gap rather than an
iteration count, and the gap at exit is a statement about the quality of the
answer, not merely of the price.

Two things make it an algorithm that returns a *schedule*. A relaxed pass may
overspend the budget, and an infeasible schedule is not an answer, so the search
ends with one capped pass at the charge it settled on — unless the best relaxed
pass already respects the budget, in which case its schedule is deliverable and
the recovery pass is skipped. And Kelley's iterates are known to zigzag, the
classical remedy being a proximal or trust-region term; on a scalar ``λ`` it is
unnecessary, but a time-varying allowance (§4.6) would need one multiplier per
quota period and a stabilised master, which is the main structural argument for
this method over a one-dimensional search.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pulp

from battery_case.modelling.milp import default_solver
from battery_case.modelling.pricing import (
    CycleOracle,
    DualBound,
    DualPoint,
    PricingResult,
)


@dataclass(frozen=True, slots=True)
class CuttingPlanePricer:
    """Minimise the dual by cutting planes. Implements ``CyclePricer``.

    ``tolerance`` is on the *relative* dual gap, so the cost is a choice rather
    than a constant: a loose tolerance spends fewer passes. ``upper_bound``
    boxes the charge, and ``max_passes`` is a stop of last resort — reaching it
    means the gap did not close, which the returned :class:`DualBound` states.
    """

    upper_bound: float = 2_000.0
    tolerance: float = 1e-4
    max_passes: int = 20

    def price(self, oracle: CycleOracle) -> PricingResult:
        """Search for the charge on relaxed passes, then recover a schedule."""
        cuts: list[DualPoint] = []
        price = 0.0
        master_value = -math.inf

        for _ in range(self.max_passes):
            cuts.append(oracle.at(price, relaxed=True))
            best_dual = min(cut.value for cut in cuts)

            master_value, next_price = solve_master(cuts, self.upper_bound)
            if best_dual - master_value <= self.tolerance * abs(best_dual):
                break
            price = next_price

        best = min(cuts, key=lambda cut: cut.value)
        bound = DualBound(value=best.value, master_value=master_value)

        # Primal recovery: a relaxed pass is an evaluation, not a deliverable.
        deliverable = best if best.feasible else oracle.at(best.price, relaxed=False)

        return PricingResult(
            price=best.price,
            schedule=deliverable.schedule,
            profit=deliverable.profit,
            cycles=deliverable.cycles,
            passes=oracle.passes,
            bound=bound,
        )


def solve_master(cuts: list[DualPoint], upper_bound: float) -> tuple[float, float]:
    """Minimise the cuts' upper envelope over ``0 <= λ <= upper_bound``.

    Returns the envelope's minimum — a lower bound on ``min_λ L(λ)`` — and the
    ``λ`` attaining it, which is where the next pass is spent::

        min  θ
        s.t. θ >= L(λ_i) + g_i (λ - λ_i)    for each cut i
             0 <= λ <= upper_bound
    """
    problem = pulp.LpProblem("dual_master", pulp.LpMinimize)
    lam = problem.add_variable("lam", 0, upper_bound)
    theta = problem.add_variable("theta", None, None)

    problem += theta
    for index, (price, value, subgradient) in enumerate(cut.cut for cut in cuts):
        problem += theta - subgradient * lam >= value - subgradient * price, f"cut_{index}"

    stats = problem.solve(default_solver())
    envelope_minimum, best_price = pulp.value(theta), pulp.value(lam)
    if stats.status is not pulp.LpSolveStatus.Optimal or envelope_minimum is None:
        raise RuntimeError(f"Dual master solved as {stats.status.name}")

    return float(envelope_minimum), float(best_price or 0.0)
