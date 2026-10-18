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
from battery_case.reporting import (
    CellValue,
    Column,
    Figure,
    SearchPlan,
    SearchSummary,
    passes_phrase,
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

    @property
    def display(self) -> SearchPlan:
        """How the method describes itself, and the three columns only it fills.

        ``passes_known`` is ``True`` here and nowhere else: the cost is
        ``1 + max_iterations`` whatever the data, so the share of the *run*
        that is done is a measurement rather than a projection, and the
        console can draw it.
        """
        return SearchPlan(
            method="bisection",
            detail=(
                f"{1 + self.max_iterations} passes "
                f"\u00b7 \u03bb \u2208 [0, {self.upper_bound:,.0f}] "
                f"\u00b7 spent within {self.tolerance:.1%} counts as used up"
            ),
            max_passes=1 + self.max_iterations,
            passes_known=True,
            columns=(
                Column("spent", "spent?", "flag"),
                Column("bracket", "bracket \u00a3/cycle", "interval"),
                Column("width", "width", "precise"),
            ),
        )

    def search(self, oracle: CycleOracle) -> DualSearchResult:
        """Find the cycle value, on capped passes, and return the plan with it."""
        reporter = oracle.reporter
        reporter.phase("calibrate", "running", f"bisection \u00b7 {self.display.detail}")
        reporter.search_started(self.display)

        spent_in_full = oracle.budget * (1.0 - self.tolerance)

        best = oracle.at(0.0, relaxed=False)
        binding = best.cycles >= spent_in_full
        reporter.pass_finished(
            oracle.pass_report(best),
            cells=_cells(best, spent_in_full, bracket=None),
        )
        if not binding:
            # The budget is not binding: no rationing is needed, and the
            # uncharged plan is already the answer. Without a line saying so,
            # a thirteen-pass method finishing in one pass reads as a crash.
            reporter.phase(
                "calibrate",
                "done",
                f"done in 1 pass of a possible {1 + self.max_iterations}",
            )
            reporter.note(
                f"the uncharged plan spends {best.cycles:,.1f} of "
                f"{oracle.budget:,.0f} cycles, so the budget never binds"
            )
            reporter.search_finished(SearchSummary(cycle_value=0.0))
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
            reporter.pass_finished(
                oracle.pass_report(point),
                cells=_cells(point, spent_in_full, bracket=(low, high)),
            )

        reporter.phase("calibrate", "done", f"bracketed \u00b7 {passes_phrase(oracle.passes)}")
        reporter.search_finished(
            SearchSummary(
                cycle_value=best_cycle_value,
                figures=(
                    Figure("bracket", (low, high), "interval"),
                    Figure("width", high - low, "precise"),
                    # The absence of a bound is a figure in its own right: a
                    # reader who is not told why there is none assumes a bug.
                    Figure(
                        "dual_bound",
                        None,
                        "money",
                        note="a capped pass reports one bit, not a slope",
                    ),
                ),
            )
        )
        return _result(best_cycle_value, best, oracle)


def _cells(
    point: DualPoint,
    spent_in_full: float,
    bracket: tuple[float, float] | None,
) -> dict[str, CellValue]:
    """The three columns this method fills, and the one bit it actually reads.

    A capped pass can never exceed the budget, so the signed overspend of the
    shared columns is uninformative here; what the method reads is whether the
    budget was *used up*, which is this one bit and nothing else. Whether that
    bit is drawn as a tick, a ``yes`` or a ``1`` is not this module's business.

    The probe pass has no bracket yet, which is ``None`` rather than a dash:
    the renderer knows what an empty cell looks like, and this does not.
    """
    return {
        "spent": point.cycles >= spent_in_full,
        "bracket": bracket,
        "width": None if bracket is None else bracket[1] - bracket[0],
    }


def _result(cycle_value: float, point: DualPoint, oracle: CycleOracle) -> DualSearchResult:
    return DualSearchResult(
        cycle_value=cycle_value,
        plan=point.plan,
        profit=point.profit,
        cycles=point.cycles,
        passes=oracle.passes,
        bound=None,
    )
