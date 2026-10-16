"""Command line entry point: ``battery-case``."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import asdict

from battery_case.data_io import load_battery_spec, load_market_prices, price_quality_report
from battery_case.data_io.paths import BATTERY_SPEC_XLSX, MARKET_PRICES_XLSX


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="battery-case", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inputs = subparsers.add_parser("inputs", help="Print the loaded battery spec and price data")
    inputs.add_argument("--spec", default=BATTERY_SPEC_XLSX, help="Path to Attachment 1")
    inputs.add_argument("--prices", default=MARKET_PRICES_XLSX, help="Path to Attachment 2")
    inputs.set_defaults(func=_cmd_inputs)

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


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
