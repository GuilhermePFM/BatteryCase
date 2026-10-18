"""Solve the horizon as one MILP, for comparison with the rolling decomposition."""

from __future__ import annotations

import sys
import time

import pulp

from battery_case.data_io.loaders import load_battery_spec, load_market_prices
from battery_case.modelling.parameters import ModelParameters
from battery_case.modelling.periods import build_periods
from battery_case.modelling.window_problem import build_problem

days = int(sys.argv[1]) if len(sys.argv) > 1 else 0  # 0 = whole horizon
time_limit = float(sys.argv[2]) if len(sys.argv) > 2 else 3600.0

spec = load_battery_spec()
prices = load_market_prices()
settlement = build_periods(prices)
if days:
    settlement = settlement.window(0, days * 48)
params = ModelParameters.from_spec(spec)

print(
    f"periods={len(settlement)} days={len(settlement) / 48:.0f} time_limit={time_limit:.0f}s",
    flush=True,
)

t0 = time.perf_counter()
problem, variables = build_problem(settlement, params)
build_seconds = time.perf_counter() - t0
print(f"build_seconds={build_seconds:.1f}", flush=True)

t0 = time.perf_counter()
stats = problem.solve(pulp.HiGHS(msg=True, timeLimit=time_limit))
solve_seconds = time.perf_counter() - t0

objective = pulp.value(problem.objective)
print(f"status={stats.status.name}", flush=True)
print(f"solve_seconds={solve_seconds:.1f}", flush=True)
print(f"objective_gbp={objective if objective is None else round(objective, 2)}", flush=True)
