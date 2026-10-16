"""Smoke tests for the command line entry point."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from battery_case.cli import main
from battery_case.data_io.paths import BATTERY_SPEC_XLSX, MARKET_PRICES_XLSX

requires_spreadsheets = pytest.mark.skipif(
    not (BATTERY_SPEC_XLSX.exists() and MARKET_PRICES_XLSX.exists()),
    reason="raw spreadsheets are not present",
)


@requires_spreadsheets
def test_inputs_command_runs(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["inputs"]) == 0

    out = capsys.readouterr().out
    assert "Battery spec" in out
    assert "Market 1 (half-hourly)" in out


@requires_spreadsheets
def test_dispatch_command_solves_a_short_horizon_and_writes_a_schedule(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "schedule.csv"
    assert (
        main(["dispatch", "--start", "2018-01-01", "--end", "2018-01-02", "--out", str(out)]) == 0
    )

    printed = capsys.readouterr().out
    assert "profit_gbp" in printed

    schedule = pd.read_csv(out, index_col=0, parse_dates=True)
    # Two whole days of half-hourly periods, and the dates asked for.
    assert len(schedule) == 96
    assert schedule.index[0] == pd.Timestamp("2018-01-01 00:00")
    assert schedule.index[-1] == pd.Timestamp("2018-01-02 23:30")
    assert schedule["revenue_gbp"].sum() > 0
