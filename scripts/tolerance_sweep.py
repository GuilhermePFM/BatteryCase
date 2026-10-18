"""What the cutting-plane tolerance buys, in passes (§6).

    uv run python scripts/tolerance_sweep.py [days] [tolerance ...] [--out PATH]

Bisection always spends ``1 + 12`` passes. The cutting-plane method stops on a
measured dual gap instead, so its cost is a choice: this is the table of that
choice in
[`cycle-value-experiments.md`](../docs/model/cycle-value-experiments.md), one
row per tolerance, on one instance.

As in the sweep, the budget is **half** what the horizon spends unpriced, so the
cap binds hard and there is something to ration. Every row solves the instance
from scratch — the oracle's cache is per search — so the cost is one full
search per tolerance.
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

from battery_case.data_io.loaders import load_battery_spec, load_market_prices
from battery_case.data_io.paths import PROJECT_ROOT
from battery_case.modelling.cycle_value.cutting_plane import CuttingPlaneSearch
from battery_case.modelling.cycle_value.oracle import CycleOracle
from battery_case.modelling.parameters import ModelParameters
from battery_case.modelling.periods import build_periods
from battery_case.modelling.rolling_horizon import PERIODS_PER_DAY, RollingPolicy

#: The instance the write-up tabulates, in days.
DEFAULT_DAYS = 30

#: Tolerances on the relative dual gap, loosest first — the default `1e-4` among them.
DEFAULT_TOLERANCES = (1e-2, 1e-3, 1e-4, 1e-5)

#: Where the rows land, beside the other measurement tables of the write-up.
OUT = PROJECT_ROOT / "docs" / "model" / "cycle-value-tolerance.csv"

FIELDS = (
    "days",
    "periods",
    "budget_cycles",
    "tolerance",
    "passes",
    "seconds",
    "lambda",
    "profit_gbp",
    "bound_gbp",
    "gap_pct",
)


def parse_args(argv: list[str]) -> tuple[int, tuple[float, ...], Path]:
    """The instance, the tolerances to try, and the CSV to write."""
    positional: list[str] = []
    out = OUT

    arguments = iter(argv)
    for argument in arguments:
        if argument == "--out":
            out = Path(next(arguments))
        else:
            positional.append(argument)

    days = int(positional[0]) if positional else DEFAULT_DAYS
    tolerances = tuple(float(value) for value in positional[1:]) or DEFAULT_TOLERANCES
    return days, tolerances, out


days, tolerances, out = parse_args(sys.argv[1:])

settlement = build_periods(load_market_prices()).window(0, days * PERIODS_PER_DAY)
spec = load_battery_spec()

unpriced = RollingPolicy().dispatch(settlement, ModelParameters.from_spec(spec))
budget = 0.5 * float(unpriced["cycles"].iloc[-1])
params = ModelParameters.from_spec(spec, cycle_budget=budget)
print(
    f"instance: {days} days, {len(settlement):,} periods, "
    f"budget {budget:.2f} cycles (half of unpriced use)\n"
)

header = (
    f"{'tolerance':>10}{'passes':>9}{'lambda':>10}{'profit':>13}{'bound':>13}{'gap':>10}{'secs':>9}"
)
print(header)
print("-" * len(header))

rows: list[dict[str, object]] = []
for tolerance in tolerances:
    started = time.perf_counter()
    result = CuttingPlaneSearch(tolerance=tolerance).search(
        CycleOracle(settlement=settlement, params=params)
    )
    seconds = time.perf_counter() - started

    # Only the cutting-plane method is run here, and it always returns a bound.
    assert result.bound is not None
    gap = 100 * result.bound.relative_gap
    rows.append(
        {
            "days": days,
            "periods": len(settlement),
            "budget_cycles": round(budget, 4),
            "tolerance": tolerance,
            "passes": result.passes,
            "seconds": round(seconds, 1),
            "lambda": round(result.cycle_value, 2),
            "profit_gbp": round(result.profit, 2),
            "bound_gbp": round(result.bound.lagrangian, 2),
            "gap_pct": round(gap, 4),
        }
    )
    print(
        f"{tolerance:>10.0e}{result.passes:>9}{result.cycle_value:>10.2f}"
        f"{result.profit:>13,.2f}{result.bound.lagrangian:>13,.2f}"
        f"{gap:>9.3f}%{seconds:>9.1f}",
        flush=True,
    )

out.parent.mkdir(parents=True, exist_ok=True)
with out.open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
print(f"\nwritten to {out}")
