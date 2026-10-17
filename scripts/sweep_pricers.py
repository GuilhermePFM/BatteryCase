"""Both pricing methods of §6 over progressively longer horizons.

    uv run python scripts/sweep_pricers.py [days ... | all] [options]

    --pricer NAME   only this method (repeatable; default: every method)
    --no-exact      skip the one-shot MILP, which has no hope past ~90 days
    --out NAME      CSV to write under docs/model/ (default cycle-price-sweep.csv)

For each horizon the cycle budget is set to **half** what the horizon spends
unpriced, so the cap binds hard and the methods have something to disagree
about. Where the capped program can be solved whole inside
:data:`EXACT_TIME_LIMIT`, it is, to give the row a ground truth; otherwise the
exact column records the status HiGHS stopped at.

Writes its CSV alongside the printed table, the way ``tractability.csv``
carries the window-length measurements.
"""

from __future__ import annotations

import csv
import sys
import time
from collections.abc import Sequence

import pulp

from battery_case.data_io.loaders import load_battery_spec, load_market_prices
from battery_case.data_io.paths import PROJECT_ROOT
from battery_case.modelling.grid import build_grid
from battery_case.modelling.milp import build_problem, default_solver
from battery_case.modelling.parameters import ModelParameters
from battery_case.modelling.pricers import PRICERS
from battery_case.modelling.pricing import CycleOracle
from battery_case.modelling.rolling import PERIODS_PER_DAY, RollingDispatcher

#: Horizons to sweep, in days — the progression of ``tractability.csv``.
DEFAULT_DAYS = (1, 2, 4, 7, 14, 30, 60, 90)

#: Longest the one-shot MILP is given before its row is left without a truth.
EXACT_TIME_LIMIT = 300.0

#: Column prefix each method writes under, kept short for the CSV header.
PREFIXES = {"bisection": "bisection", "cutting-plane": "cutting"}

EXACT_FIELDS = (
    "exact_status",
    "exact_seconds",
    "exact_profit_gbp",
    "exact_best_bound_gbp",
    "exact_gap_pct",
)


def parse_args(
    argv: Sequence[str], whole_days: int
) -> tuple[tuple[int, ...], tuple[str, ...], bool, str]:
    """Days to sweep, methods to run, whether to solve exactly, and the CSV name."""
    days: list[int] = []
    pricers: list[str] = []
    solve_exactly = True
    out = "cycle-price-sweep.csv"

    arguments = iter(argv)
    for argument in arguments:
        if argument == "--no-exact":
            solve_exactly = False
        elif argument == "--pricer":
            pricers.append(next(arguments))
        elif argument == "--out":
            out = next(arguments)
        elif argument == "all":
            days.append(whole_days)
        else:
            days.append(int(argument))

    unknown = [name for name in pricers if name not in PRICERS]
    if unknown:
        raise SystemExit(f"unknown pricer(s): {', '.join(unknown)}; have {', '.join(PRICERS)}")

    return (
        tuple(days) or DEFAULT_DAYS,
        tuple(pricers) or tuple(PRICERS),
        solve_exactly,
        out,
    )


whole_grid = build_grid(load_market_prices())
days_to_sweep, pricers_to_run, solve_exactly, out_name = parse_args(
    sys.argv[1:], len(whole_grid) // PERIODS_PER_DAY
)
spec = load_battery_spec()

fields: list[str] = ["days", "periods", "budget_cycles"]
if solve_exactly:
    fields += EXACT_FIELDS
for name in pricers_to_run:
    prefix = PREFIXES[name]
    fields += [
        f"{prefix}_passes",
        f"{prefix}_seconds",
        f"{prefix}_lambda",
        f"{prefix}_profit_gbp",
        f"{prefix}_bound_gbp",
        f"{prefix}_gap_pct",
    ]
compares = len(pricers_to_run) > 1
if compares:
    fields.append("profit_delta_pct")
if solve_exactly:
    fields.append("bound_above_exact")

header = f"{'days':>5}{'budget':>9}"
if solve_exactly:
    header += f"{'exact':>12}"
for name in pricers_to_run:
    short = name[:3]
    header += (
        f"{short + ' pass':>10}{short + ' λ':>9}{short + ' profit':>13}"
        f"{short + ' bound':>13}{short + ' gap':>10}{short + ' secs':>10}"
    )
print(header)
print("-" * len(header))

rows: list[dict[str, object]] = []
for days in days_to_sweep:
    grid = whole_grid.window(0, days * PERIODS_PER_DAY)

    unpriced = RollingDispatcher().run_on_grid(grid, ModelParameters.from_spec(spec))
    budget = 0.5 * float(unpriced["cycles"].iloc[-1])
    params = ModelParameters.from_spec(spec, cycle_budget=budget)

    row: dict[str, object] = {
        "days": days,
        "periods": len(grid),
        "budget_cycles": round(budget, 4),
    }
    line = f"{days:>5}{budget:>9.2f}"

    if solve_exactly:
        started = time.perf_counter()
        problem, _ = build_problem(grid, params)
        stats = problem.solve(default_solver(time_limit=EXACT_TIME_LIMIT))
        objective = pulp.value(problem.objective)
        row["exact_status"] = stats.status.name
        row["exact_seconds"] = round(time.perf_counter() - started, 1)
        row["exact_profit_gbp"] = None if objective is None else round(float(objective), 2)
        row["exact_best_bound_gbp"] = (
            None if stats.best_bound is None else round(float(stats.best_bound), 2)
        )
        row["exact_gap_pct"] = (
            None if stats.gap_rel is None else round(100 * float(stats.gap_rel), 4)
        )
        exact = row["exact_profit_gbp"]
        cell = "—" if exact is None else f"{float(exact):,.2f}"  # type: ignore[arg-type]
        line += f"{cell if row['exact_status'] == 'Optimal' else '~' + cell:>12}"

    for name in pricers_to_run:
        prefix = PREFIXES[name]
        started = time.perf_counter()
        result = PRICERS[name].price(CycleOracle(grid=grid, params=params))
        seconds = round(time.perf_counter() - started, 1)
        row[f"{prefix}_passes"] = result.passes
        row[f"{prefix}_seconds"] = seconds
        row[f"{prefix}_lambda"] = round(result.price, 2)
        row[f"{prefix}_profit_gbp"] = round(result.profit, 2)
        bound = None if result.bound is None else round(result.bound.value, 2)
        gap = None if result.bound is None else round(100 * result.bound.relative_gap, 4)
        row[f"{prefix}_bound_gbp"] = bound
        row[f"{prefix}_gap_pct"] = gap
        line += (
            f"{result.passes:>10}{result.price:>9.2f}{result.profit:>13,.2f}"
            f"{'—' if bound is None else format(bound, ',.2f'):>13}"
            f"{'—' if gap is None else format(gap, '.3f') + '%':>10}{seconds:>10.1f}"
        )

    if compares:
        bisection_profit = float(row["bisection_profit_gbp"])  # type: ignore[arg-type]
        cutting_profit = float(row["cutting_profit_gbp"])  # type: ignore[arg-type]
        row["profit_delta_pct"] = round(100 * (cutting_profit / bisection_profit - 1), 4)

    if solve_exactly:
        exact = row["exact_profit_gbp"]
        certificate = row.get("cutting_bound_gbp")
        row["bound_above_exact"] = (
            None
            if exact is None or certificate is None or row["exact_status"] != "Optimal"
            else bool(float(certificate) >= float(exact) - 0.01)  # type: ignore[arg-type]
        )

    print(line, flush=True)
    rows.append(row)

out = PROJECT_ROOT / "docs" / "model" / out_name
with out.open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
print(f"\nwritten to {out}")
