"""Finding the cycle value by Kelley's cutting-plane method (§6).

The dual function ``L(λ)`` of §6 is convex and piecewise linear, being a
pointwise maximum of functions affine in ``λ``, and each pass of the *relaxed*
problem hands back both its Lagrangian and an exact subgradient. So each pass
contributes a **cut**: a linear function lying everywhere below ``L``. The next
cycle value to try is the minimiser of the cuts' upper envelope — a two-variable
linear program with one row per pass, negligible beside the pass itself.

The method then brackets its own answer. The best ``L(λ)`` evaluated is an upper
bound on ``min_λ L(λ)``, and by weak duality on the constrained optimum as well;
the master's envelope minimum is a lower bound on the same quantity, the cuts
being underestimators. The loop therefore stops on a measured gap rather than an
iteration count, and the gap at exit is a statement about the quality of the
answer, not merely of the cycle value.

Two things make it an algorithm that returns a *plan*. A relaxed pass may
overspend the budget, and an infeasible plan is not an answer, so the search
ends with one capped pass at the value it settled on — unless the best relaxed
pass already respects the budget, in which case its plan is deliverable and
the recovery pass is skipped. And Kelley's iterates are known to zigzag, the
classical remedy being a proximal or trust-region term; on a scalar ``λ`` it is
unnecessary, but a time-varying allowance (§4.6) would need one multiplier per
quota period and a stabilised master, which is the main structural argument for
this method over a one-dimensional search.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

import pulp

from battery_case.modelling.cycle_value.oracle import (
    CycleOracle,
    DualBound,
    DualPoint,
    DualSearchResult,
)
from battery_case.modelling.window_problem import default_solver
from battery_case.reporting import (
    Column,
    Figure,
    SearchPlan,
    SearchSummary,
    passes_phrase,
)


@dataclass(frozen=True, slots=True)
class CuttingPlaneSearch:
    """Minimise the dual by cutting planes. Implements ``DualSearch``.

    ``tolerance`` is on the *relative* dual gap, so the cost is a choice rather
    than a constant: a loose tolerance spends fewer passes. ``upper_bound``
    boxes the cycle value, and ``max_passes`` is a stop of last resort — reaching it
    means the gap did not close, which the returned :class:`DualBound` states.
    """

    upper_bound: float = 2_000.0
    tolerance: float = 1e-4
    max_passes: int = 20

    @property
    def display(self) -> SearchPlan:
        """How the method describes itself, and the two columns only it fills."""
        return SearchPlan(
            method="cutting-plane",
            detail=(
                f"gap \u2264 {self.tolerance:.2%} \u00b7 \u2264 {self.max_passes} passes "
                f"\u00b7 \u03bb \u2208 [0, {self.upper_bound:,.0f}]"
            ),
            max_passes=self.max_passes,
            passes_known=False,
            columns=(
                Column("lagrangian", "L(\u03bb) \u00a3", "money"),
                Column("gap", "gap", "percent"),
            ),
            tolerance=self.tolerance,
        )

    def search(self, oracle: CycleOracle) -> DualSearchResult:
        """Search for the cycle value on relaxed passes, then recover a plan."""
        reporter = oracle.reporter
        reporter.phase("calibrate", "running", f"cutting-plane \u00b7 {self.display.detail}")
        reporter.search_started(self.display)

        cuts: list[DualPoint] = []
        cycle_value = 0.0
        envelope = -math.inf

        for _ in range(self.max_passes):
            cuts.append(oracle.at(cycle_value, relaxed=True))
            best_dual = min(cut.lagrangian for cut in cuts)

            started = time.perf_counter()
            envelope, next_cycle_value = solve_master(cuts, self.upper_bound)
            master_ms = 1e3 * (time.perf_counter() - started)

            converged = best_dual - envelope <= self.tolerance * abs(best_dual)
            self._report_pass(oracle, cuts, envelope, next_cycle_value, master_ms, converged)
            if converged:
                break
            cycle_value = next_cycle_value

        best = min(cuts, key=lambda cut: cut.lagrangian)
        bound = DualBound(lagrangian=best.lagrangian, envelope=envelope)
        reporter.phase("calibrate", "done", f"converged \u00b7 {passes_phrase(oracle.passes)}")
        reporter.search_finished(
            SearchSummary(
                cycle_value=best.cycle_value,
                figures=(
                    Figure("dual_gap", bound.relative_gap, "percent"),
                    Figure(
                        "profit_bound",
                        bound.lagrangian,
                        "money",
                        unit="\u00a3",
                        note="weak-duality bound on the constrained optimum",
                    ),
                ),
            )
        )

        deliverable = self._recover(oracle, best)

        return DualSearchResult(
            cycle_value=best.cycle_value,
            plan=deliverable.plan,
            profit=deliverable.profit,
            cycles=deliverable.cycles,
            passes=oracle.passes,
            bound=bound,
        )

    def _report_pass(
        self,
        oracle: CycleOracle,
        cuts: list[DualPoint],
        envelope: float,
        next_cycle_value: float,
        master_ms: float,
        converged: bool,
    ) -> None:
        """Announce the cut the pass just bought, and what the master did with it.

        The three numbers below do not exist until the pass ends, and they are
        the method's whole argument for itself: a slope, an envelope that is a
        real lower bound, and a next ``λ`` that is a decision rather than a step.
        """
        reporter = oracle.reporter
        point = cuts[-1]
        best_dual = min(cut.lagrangian for cut in cuts)
        gap = (best_dual - envelope) / abs(best_dual) if best_dual else 0.0

        reporter.pass_finished(
            oracle.pass_report(point, gap=gap),
            cells={"lagrangian": point.lagrangian, "gap": gap},
        )
        reporter.note(
            f"cut {len(cuts)}   L \u2265 {point.lagrangian:,.0f} "
            f"+ ({point.subgradient:,.1f})\u00b7(\u03bb \u2212 {point.cycle_value:,.2f})"
        )
        reporter.note(
            f"master  {len(cuts)} cuts \u00b7 2 vars \u00b7 {master_ms:,.0f} ms"
            f"      envelope {envelope:,.0f}"
        )
        if not converged:
            reporter.note(f"next \u03bb  {next_cycle_value:,.2f}   = envelope minimiser")

    def _recover(self, oracle: CycleOracle, best: DualPoint) -> DualPoint:
        """Turn the best evaluation into a deliverable plan, or say why none is needed.

        A relaxed pass is an evaluation, not a deliverable. This step therefore
        sometimes runs and sometimes does not, which is exactly why it has to
        report *both* outcomes — an unannounced sixth pass after a converged
        search reads as a bug, and a silently skipped one reads as an omission.
        """
        reporter = oracle.reporter
        if best.within_budget:
            reporter.phase(
                "recover",
                "done",
                f"skipped, the relaxed plan is already within budget ({best.cycles:,.1f} cycles)",
            )
            return best

        reporter.phase(
            "recover",
            "running",
            f"capped at {oracle.budget:,.0f} cycles \u00b7 \u03bb = {best.cycle_value:,.2f}",
        )
        reporter.note(
            f"why  the best relaxed pass spent {best.cycles:,.1f} cycles, "
            f"{best.cycles / oracle.budget - 1:.1%} over budget \u2014"
        )
        reporter.note("     a relaxed pass is an evaluation, not a deliverable plan")

        # A capped pass has no cut and no envelope, so it fills neither of this
        # method's columns; leaving them out is what draws them empty.
        capped = oracle.at(best.cycle_value, relaxed=False, label="recovery")
        reporter.pass_finished(oracle.pass_report(capped, recovery=True))
        reporter.phase("recover", "done", "plan is within budget", elapsed=capped.elapsed)
        return capped


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
    for index, (cycle_value, lagrangian, subgradient) in enumerate(cut.cut for cut in cuts):
        problem += (
            theta - subgradient * lam >= lagrangian - subgradient * cycle_value,
            f"cut_{index}",
        )

    stats = problem.solve(default_solver())
    envelope_minimum, best_lam = pulp.value(theta), pulp.value(lam)
    if stats.status is not pulp.LpSolveStatus.Optimal or envelope_minimum is None:
        raise RuntimeError(f"Dual master solved as {stats.status.name}")

    return float(envelope_minimum), float(best_lam or 0.0)
