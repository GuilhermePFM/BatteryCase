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
from battery_case.modelling import ModelParameters, RollingDispatcher, build_grid, summarise
from battery_case.modelling.grid import DispatchGrid
from battery_case.modelling.pricers import PRICERS, CalibratedDispatcher, pricer_named
from battery_case.modelling.rolling import PERIODS_PER_DAY


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
        "--cycle-price",
        type=float,
        default=0.0,
        help="Charge in GBP per equivalent full cycle used (default: 0)",
    )
    dispatch.add_argument(
        "--cycle-pricer",
        choices=sorted(PRICERS),
        help=(
            "Search for the cycle charge instead of taking --cycle-price, "
            "by this method (§6). Costs one pass over the horizon per step"
        ),
    )
    dispatch.add_argument(
        "--out",
        default=RESULTS_DIR / "dispatch_schedule.csv",
        help="Where to write the half-hourly schedule (.csv, or .parquet)",
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
    grid = build_grid(prices).between(args.start, _end_of_day(args.end))
    dispatcher = RollingDispatcher(
        commit_periods=args.commit_days * PERIODS_PER_DAY,
        lookahead_periods=args.lookahead_days * PERIODS_PER_DAY,
        cycle_price=args.cycle_price,
        on_window=_progress,
    )

    print(
        f"Dispatching {len(grid):,} half-hourly periods "
        f"({grid.timestamps[0]:%Y-%m-%d} to {grid.timestamps[-1]:%Y-%m-%d}) "
        f"in windows of {args.commit_days}d + {args.lookahead_days}d lookahead",
        flush=True,
    )

    if args.cycle_pricer:
        schedule = _priced_dispatch(args.cycle_pricer, dispatcher, grid, params)
    else:
        schedule = dispatcher.run_on_grid(grid, params)
    print(file=sys.stderr)

    print("\nResults")
    for field, value in summarise(schedule, params).items():
        print(f"  {field:<30} {value:>16,.2f}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix == ".parquet":
        schedule.to_parquet(out)
    else:
        schedule.to_csv(out)
    print(f"\nSchedule written to {out}")
    return 0


def _priced_dispatch(
    method: str,
    dispatcher: RollingDispatcher,
    grid: DispatchGrid,
    params: ModelParameters,
) -> pd.DataFrame:
    """Search for the cycle charge, report what the search cost and proved."""
    print(f"  pricing the {params.cycle_budget:,.0f}-cycle budget by {method} (§6)", flush=True)
    result = CalibratedDispatcher(
        pricer=pricer_named(method), dispatcher=dispatcher
    ).price_and_dispatch(grid, params)
    print(file=sys.stderr)

    print(f"\n  cycle charge                   {result.price:>16,.2f} GBP/cycle")
    print(f"  horizon passes spent           {result.passes:>16,d}")
    if result.bound is None:
        # Bisection reads one bit per pass and has no bound to offer (§6).
        print("  dual bound                     " + f"{'not available':>16}")
    else:
        print(f"  dual bound on profit           {result.bound.value:>16,.2f} GBP")
        print(f"  dual gap                       {result.bound.relative_gap:>15.3%}")
    return result.schedule


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
