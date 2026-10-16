"""Checks that the supplied spreadsheets load into the expected shapes."""

from __future__ import annotations

import pandas as pd
import pytest

from battery_case.data_io import load_battery_spec, load_market_prices, price_quality_report
from battery_case.data_io.paths import BATTERY_SPEC_XLSX, MARKET_PRICES_XLSX

pytestmark = pytest.mark.skipif(
    not (BATTERY_SPEC_XLSX.exists() and MARKET_PRICES_XLSX.exists()),
    reason="raw spreadsheets are not present",
)


def test_battery_spec_matches_attachment_1() -> None:
    spec = load_battery_spec()

    assert spec.max_charge_rate_mw == 2.0
    assert spec.max_discharge_rate_mw == 2.0
    assert spec.max_storage_volume_mwh == 4.0
    assert spec.charging_loss_fraction == 0.05
    assert spec.discharging_loss_fraction == 0.05
    assert spec.lifetime_years == 10.0
    assert spec.lifetime_cycles == 5000.0
    assert spec.degradation_pct_per_cycle == 0.001
    assert spec.capex_gbp == 500_000.0
    assert spec.fixed_opex_gbp_per_year == 5_000.0


def test_market_prices_cover_2018_to_2020_at_their_native_resolution() -> None:
    prices = load_market_prices()

    assert len(prices.market_1) == 52_608
    assert len(prices.market_2) == 26_304
    assert prices.start == pd.Timestamp("2018-01-01 00:00")
    assert prices.end == pd.Timestamp("2020-12-31 23:30")
    assert prices.market_1.notna().all()
    assert prices.market_2.notna().all()


def test_quality_report_flags_the_clock_change_artefacts() -> None:
    report = price_quality_report(load_market_prices())

    # Two half hours are repeated at each of the three spring clock changes.
    assert report.loc["market_1", "duplicate_timestamps"] == 6
    assert not report.loc["market_1", "monotonic"]

    # Market 2's timestamps are clean once rounded to the minute.
    assert report.loc["market_2", "duplicate_timestamps"] == 0
    assert report.loc["market_2", "irregular_steps"] == 0
    assert report.loc["market_2", "monotonic"]


def test_between_restricts_both_markets() -> None:
    day = load_market_prices().between("2018-01-01", "2018-01-01 23:59")

    assert len(day.market_1) == 48
    assert len(day.market_2) == 24
