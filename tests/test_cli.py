"""Smoke tests for the command line entry point."""

from __future__ import annotations

import json
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
    out = tmp_path / "plan.csv"
    assert (
        main(["dispatch", "--start", "2018-01-01", "--end", "2018-01-02", "--out", str(out)]) == 0
    )

    printed = capsys.readouterr().out
    # The result goes to stdout in two named blocks: what the battery does,
    # and how far that could be from the best possible.
    assert "Plan" in printed
    assert "profit" in printed
    assert "Certificate" in printed
    assert "cycle value" in printed

    plan = pd.read_csv(out, index_col=0, parse_dates=True)
    # Two whole days of half-hourly periods, and the dates asked for.
    assert len(plan) == 96
    assert plan.index[0] == pd.Timestamp("2018-01-01 00:00")
    assert plan.index[-1] == pd.Timestamp("2018-01-02 23:30")
    assert plan["net_revenue_gbp"].sum() > 0


@requires_spreadsheets
def test_quiet_keeps_the_result_on_stdout_and_says_nothing_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``> summary.txt`` must still capture the answer, whatever the progress mode."""
    out = tmp_path / "plan.csv"
    argv = [
        "dispatch", "--start", "2018-01-01", "--end", "2018-01-01",
        "--out", str(out), "--quiet",
    ]
    assert main(argv) == 0

    captured = capsys.readouterr()
    assert "Plan" in captured.out
    assert captured.err == ""


@requires_spreadsheets
def test_json_progress_writes_parsable_events_to_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A sweep should be able to replay a run's convergence without re-running it."""
    out = tmp_path / "plan.csv"
    argv = [
        "dispatch", "--start", "2018-01-01", "--end", "2018-01-01",
        "--out", str(out), "--progress", "json",
    ]
    assert main(argv) == 0

    events = [json.loads(line) for line in capsys.readouterr().err.splitlines() if line.strip()]
    kinds = {event["event"] for event in events}
    assert {"run_started", "pass_started", "pass_finished", "run_finished"} <= kinds

    finished = [event for event in events if event["event"] == "pass_finished"]
    assert finished and all("cycles" in event and "mode" in event for event in finished)
