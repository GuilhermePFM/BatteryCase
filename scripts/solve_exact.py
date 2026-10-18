"""Solve the horizon as one MILP, for comparison with the rolling decomposition.

    uv run python scripts/solve_exact.py [days] [time_limit_seconds] [--csv PATH]

``days`` is taken from the start of the price data, 0 meaning the whole horizon.
``--csv`` records the row in the measurement table of
[`tractability.md`](../docs/model/tractability.md) — one row per window length,
replaced in place when the same length is measured again, so the file can be
rebuilt window by window.
"""

from __future__ import annotations

import csv
import math
import sys
import time
from pathlib import Path

import pulp

from battery_case.data_io.loaders import load_battery_spec, load_market_prices
from battery_case.modelling.parameters import ModelParameters
from battery_case.modelling.periods import build_periods
from battery_case.modelling.window_problem import build_problem

#: Columns of ``tractability.csv``, in the order that file carries them.
FIELDS = (
    "window_days",
    "periods",
    "status",
    "solve_seconds",
    "objective_gbp",
    "best_bound_gbp",
    "gap_pct",
)


def parse_args(argv: list[str]) -> tuple[int, float, Path | None]:
    """``days``, the time limit, and the CSV to record the row in."""
    positional: list[str] = []
    csv_path: Path | None = None

    arguments = iter(argv)
    for argument in arguments:
        if argument == "--csv":
            csv_path = Path(next(arguments))
        else:
            positional.append(argument)

    days = int(positional[0]) if positional else 0  # 0 = whole horizon
    time_limit = float(positional[1]) if len(positional) > 1 else 3600.0
    return days, time_limit, csv_path


def record(row: dict[str, object], out: Path) -> None:
    """Write ``row`` into ``out``, replacing any row for the same window length.

    One window length is one measurement, so re-measuring 30 days should leave
    one 30-day row rather than two. Rows are kept in window order, which is the
    order the table in the write-up reads them.
    """
    existing: list[dict[str, str]] = []
    if out.exists():
        with out.open(newline="") as handle:
            existing = [
                line
                for line in csv.DictReader(handle)
                if int(line["window_days"]) != int(row["window_days"])  # type: ignore[arg-type]
            ]

    merged = [*existing, {name: "" if row[name] is None else str(row[name]) for name in FIELDS}]
    merged.sort(key=lambda line: int(line["window_days"]))

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(merged)
    print(f"recorded in {out}", flush=True)


days, time_limit, csv_out = parse_args(sys.argv[1:])

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

# No incumbent inside the limit is a blank, not a zero: pulp evaluates the
# objective expression over unset variables as 0.0, which would read as a plan
# worth nothing rather than as no plan at all.
objective = pulp.value(problem.objective) if stats.has_solution else None
print(f"status={stats.status.name}", flush=True)
print(f"solve_seconds={solve_seconds:.1f}", flush=True)
print(f"objective_gbp={objective if objective is None else round(objective, 2)}", flush=True)
print(
    f"best_bound_gbp={None if stats.best_bound is None else round(float(stats.best_bound), 2)}",
    flush=True,
)

if csv_out is not None:
    record(
        {
            "window_days": len(settlement) // 48,
            "periods": len(settlement),
            "status": stats.status.name,
            "solve_seconds": round(solve_seconds, 1),
            "objective_gbp": None if objective is None else round(float(objective), 2),
            "best_bound_gbp": (
                None if stats.best_bound is None else round(float(stats.best_bound), 2)
            ),
            "gap_pct": (
                None
                if stats.gap_rel is None or not math.isfinite(float(stats.gap_rel))
                else round(100 * float(stats.gap_rel), 2)
            ),
        },
        csv_out,
    )
