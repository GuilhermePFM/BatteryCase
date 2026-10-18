"""Run every pricing method of §6 over one instance and tabulate what each cost.

    uv run python scripts/compare_searches.py [days] [cycle_budget]

``days`` is taken from the start of the price data, ``cycle_budget`` in
equivalent full cycles — pass a budget below what the horizon would spend
unpriced, or the cap does not bind and every method returns zero in one pass.
With no budget given, half the unpriced use is measured first and used, which is
the instance where the methods have something to disagree about.

Where the horizon is short enough, the capped program is also solved whole, as
one MILP, to give the comparison a ground truth the decomposition cannot
provide itself.
"""

from __future__ import annotations

import sys
import time

import pulp

from battery_case.data_io.loaders import load_battery_spec, load_market_prices
from battery_case.modelling.dual_problem import CycleOracle
from battery_case.modelling.dual_search import SEARCHES
from battery_case.modelling.parameters import ModelParameters
from battery_case.modelling.periods import build_periods
from battery_case.modelling.rolling_horizon import PERIODS_PER_DAY, RollingPolicy
from battery_case.modelling.window_problem import build_problem, default_solver

#: Above this, one MILP over the whole instance is not worth waiting for (§6).
EXACT_LIMIT_DAYS = 30

days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
budget = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0

settlement = build_periods(load_market_prices()).window(0, days * PERIODS_PER_DAY)
spec = load_battery_spec()

if not budget:
    unpriced = RollingPolicy().dispatch(settlement, ModelParameters.from_spec(spec))
    budget = 0.5 * float(unpriced["cycles"].iloc[-1])
    print(f"unpriced use {2 * budget:.2f} cycles, so pricing against a budget of {budget:.2f}")

params = ModelParameters.from_spec(spec, cycle_budget=budget)
print(
    f"instance: {days} days, {len(settlement):,} periods, budget {params.cycle_budget:.2f} cycles\n"
)

header = (
    f"{'method':<16}{'passes':>8}{'seconds':>10}{'lambda':>12}{'profit':>12}{'bound':>12}{'gap':>9}"
)
print(header)
print("-" * len(header))

if days <= EXACT_LIMIT_DAYS:
    started = time.perf_counter()
    problem, _ = build_problem(settlement, params)
    problem.solve(default_solver())
    exact = float(pulp.value(problem.objective))
    print(
        f"{'exact (1 MILP)':<16}{'—':>8}{time.perf_counter() - started:>10.1f}"
        f"{'—':>12}{exact:>12,.2f}{'optimal':>12}{'—':>9}"
    )

for name, search in SEARCHES.items():
    started = time.perf_counter()
    result = search.price(CycleOracle(settlement=settlement, params=params))
    seconds = time.perf_counter() - started

    bound = f"{result.bound.value:,.2f}" if result.bound else "—"
    gap = f"{result.bound.relative_gap:.3%}" if result.bound else "—"
    print(
        f"{name:<16}{result.passes:>8d}{seconds:>10.1f}{result.price:>12,.2f}"
        f"{result.profit:>12,.2f}{bound:>12}{gap:>9}"
    )
