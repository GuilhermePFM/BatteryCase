"""Command line entry point: ``battery-case``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from battery_case.data_io import load_battery_spec, load_market_prices, price_quality_report
from battery_case.data_io.paths import BATTERY_SPEC_XLSX, MARKET_PRICES_XLSX, RESULTS_DIR
from battery_case.modelling import ModelParameters, RollingPolicy, build_periods, summarise
from battery_case.modelling.calibrated_policy import CalibratedPolicy
from battery_case.modelling.dual_search import DEFAULT_SEARCH, SEARCHES, search_named
from battery_case.modelling.periods import SettlementPeriods
from battery_case.modelling.rolling_horizon import PERIODS_PER_DAY


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="battery-case", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inputs = subparsers.add_parser("inputs", help="Print the loaded battery spec and price data")
    inputs.add_argument("--spec", default=BATTERY_SPEC_XLSX, help="Path to Attachment 1")
    inputs.add_argument("--prices", default=MARKET_PRICES_XLSX, help="Path to Attachment 2")
    inputs.set_defaults(func=_cmd_inputs)

    dispatch = subparsers.add_parser("dispatch", help="Solve the dispatch model and report profit")
    dispatch.add_argument("--spec", default=BATTERY_SPEC_XLSX, help="Path to Attachment 1")
    dispatch.add_argument("--prices", default=MARKET_PRICES_XLSX, help="Path to Attachment 2")
    dispatch.add_argument("--start", help="First timestamp to dispatch over (default: all data)")
    dispatch.add_argument("--end", help="Last timestamp to dispatch over (default: all data)")
    dispatch.add_argument(
        "--commit-days",
        type=int,
        default=1,
        help="Days committed per solved window (default: 1)",
    )
    dispatch.add_argument(
        "--lookahead-days",
        type=int,
        default=1,
        help="Days of foresight beyond the committed window, then discarded (default: 1)",
    )
    dispatch.add_argument(
        "--cycle-value",
        type=float,
        default=0.0,
        help="Value of one equivalent full cycle, in GBP, charged to the objective (default: 0)",
    )
    dispatch.add_argument(
        "--search",
        nargs="?",
        const=DEFAULT_SEARCH,
        choices=sorted(SEARCHES),
        help=(
            "Search for the cycle value instead of taking --cycle-value, "
            f"by this method (§6, default: {DEFAULT_SEARCH}). "
            "Costs one pass over the horizon per step"
        ),
    )
    dispatch.add_argument(
        "--out",
        default=RESULTS_DIR / "dispatch_plan.csv",
        help="Where to write the half-hourly plan (.csv, or .parquet)",
    )
    dispatch.set_defaults(func=_cmd_dispatch)

    return parser


def _cmd_inputs(args: argparse.Namespace) -> int:
    spec = load_battery_spec(args.spec)
    prices = load_market_prices(args.prices)

    print("Battery spec")
    for field, value in asdict(spec).items():
        print(f"  {field:<32} {value:>12,.10g}")

    print("\nMarket prices")
    for name, series in (
        ("Market 1 (half-hourly)", prices.market_1),
        ("Market 2 (hourly)", prices.market_2),
    ):
        print(
            f"  {name:<24} {len(series):>7,} periods  "
            f"{series.index[0]:%Y-%m-%d} to {series.index[-1]:%Y-%m-%d}  "
            f"mean £{series.mean():,.2f}/MWh"
        )

    print("\nData quality")
    print(price_quality_report(prices).to_string())
    return 0


def _cmd_dispatch(args: argparse.Namespace) -> int:
    spec = load_battery_spec(args.spec)
    prices = load_market_prices(args.prices)

    params = ModelParameters.from_spec(spec)
    settlement = build_periods(prices).between(args.start, _end_of_day(args.end))
    policy = RollingPolicy(
        commit_periods=args.commit_days * PERIODS_PER_DAY,
        lookahead_periods=args.lookahead_days * PERIODS_PER_DAY,
        cycle_value=args.cycle_value,
        on_window=_progress,
    )

    print(
        f"Dispatching {len(settlement):,} half-hourly periods "
        f"({settlement.timestamps[0]:%Y-%m-%d} to {settlement.timestamps[-1]:%Y-%m-%d}) "
        f"in windows of {args.commit_days}d + {args.lookahead_days}d lookahead",
        flush=True,
    )

    if args.search:
        plan = _calibrated_dispatch(args.search, policy, settlement, params)
    else:
        plan = policy.dispatch(settlement, params)
    print(file=sys.stderr)

    print("\nResults")
    for field, value in summarise(plan, params).items():
        print(f"  {field:<30} {value:>16,.2f}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix == ".parquet":
        plan.to_parquet(out)
    else:
        plan.to_csv(out)
    print(f"\nPlan written to {out}")
    return 0


def _calibrated_dispatch(
    method: str,
    policy: RollingPolicy,
    settlement: SettlementPeriods,
    params: ModelParameters,
) -> pd.DataFrame:
    """Search for the cycle value, report what the search cost and proved."""
    print(f"  valuing the {params.cycle_budget:,.0f}-cycle budget by {method} (§6)", flush=True)
    result = CalibratedPolicy(search=search_named(method), policy=policy).calibrate_and_dispatch(
        settlement, params
    )
    print(file=sys.stderr)

    print(f"\n  cycle value                    {result.cycle_value:>16,.2f} GBP/cycle")
    print(f"  horizon passes spent           {result.passes:>16,d}")
    if result.bound is None:
        # Bisection reads one bit per pass and has no bound to offer (§6).
        print("  dual bound                     " + f"{'not available':>16}")
    else:
        print(f"  dual bound on profit           {result.bound.lagrangian:>16,.2f} GBP")
        print(f"  dual gap                       {result.bound.relative_gap:>15.3%}")
    return result.plan


def _end_of_day(value: str | None) -> pd.Timestamp | None:
    """Read ``--end`` as inclusive of the whole day when no time is given."""
    if value is None:
        return None
    end = pd.Timestamp(value)
    return end + pd.Timedelta(days=1) if end.normalize() == end else end


def _progress(done: int, total: int) -> None:
    """One line, overwritten, so a three-year solve shows it is moving."""
    print(
        f"\r  {done:,}/{total:,} periods ({done / total:6.1%})",
        end="",
        file=sys.stderr,
        flush=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
