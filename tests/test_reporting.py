"""What a run says about itself while it runs (§6).

The assertions below are about the *contract*, not the glyphs: that a finished
pass becomes text that stays on screen, that a redirected stream never receives
cursor control, that a cache hit is reported as one, and that each method fills
its own columns. The exact box drawing is free to change.
"""

from __future__ import annotations

import io
import json
import re
from dataclasses import replace

import pandas as pd
import pytest

from battery_case.modelling.cycle_value.bisection import BisectionSearch
from battery_case.modelling.cycle_value.cutting_plane import CuttingPlaneSearch
from battery_case.modelling.cycle_value.oracle import CycleOracle
from battery_case.modelling.parameters import ModelParameters
from battery_case.modelling.periods import SettlementPeriods
from battery_case.modelling.rolling_horizon import RollingPolicy, WindowProgress
from battery_case.reporting import (
    ConsoleReporter,
    JsonReporter,
    LogReporter,
    NullReporter,
    RunPlan,
    _duration,
    _passes_to_close,
    make_reporter,
)
from tests.helpers import SPEC, make_periods

#: Same three-day instance the search tests use: a binding single-cycle budget.
BUDGET = 1.0


def _grid() -> SettlementPeriods:
    cheap = [20.0] * 24
    return make_periods(cheap + [100.0] * 24 + cheap + [100.0] * 24 + cheap + [400.0] * 24)


def _params() -> ModelParameters:
    return replace(ModelParameters.from_spec(SPEC), cycle_budget=BUDGET)


def _run(search: object, reporter: object) -> str:
    """Run a real search against the small instance and return what it printed."""
    stream = io.StringIO()
    built = reporter(stream)  # type: ignore[operator]
    oracle = CycleOracle(settlement=_grid(), params=_params(), reporter=built)
    search.search(oracle)  # type: ignore[attr-defined]
    return stream.getvalue()


# -- the seam ------------------------------------------------------------


def test_a_search_runs_silent_by_default() -> None:
    """Nothing has to opt out of being quiet: a test or a notebook just works."""
    oracle = CycleOracle(settlement=_grid(), params=_params())

    assert isinstance(oracle.reporter, NullReporter)
    assert CuttingPlaneSearch().search(oracle).passes >= 1


def test_the_window_callback_carries_where_the_pass_has_reached() -> None:
    """A period count cannot say *when* in the horizon a pass is, and a reader needs that."""
    seen: list[WindowProgress] = []
    policy = RollingPolicy(commit_periods=24, lookahead_periods=24, on_window=seen.append)

    policy.dispatch(_grid(), _params())

    assert len(seen) == policy.window_count(len(_grid()))
    assert [progress.window for progress in seen] == list(range(1, len(seen) + 1))
    assert seen[-1].fraction == pytest.approx(1.0)
    assert seen[0].at < seen[-1].at


def test_the_pass_count_is_known_up_front() -> None:
    """The run bar is only honest because the pass length is arithmetic, not a guess."""
    assert RollingPolicy(commit_periods=48).window_count(52_608) == 1_096
    assert RollingPolicy(commit_periods=48).window_count(100) == 3  # a part window still counts


# -- what each method fills ----------------------------------------------


def test_cutting_planes_report_the_cut_the_envelope_and_the_next_value() -> None:
    """The three numbers that only exist once a pass ends are the method's whole argument."""
    printed = _run(CuttingPlaneSearch(), LogReporter)

    assert "method=cutting-plane" in printed
    assert "cut 1" in printed and "envelope" in printed
    assert "envelope minimiser" in printed
    assert "mode=relaxed" in printed
    assert "weak-duality bound" in printed


def test_bisection_reports_the_bracket_and_refuses_to_quote_a_bound() -> None:
    """One bit per pass buys a bracket and nothing else, and the output must say so."""
    printed = _run(BisectionSearch(upper_bound=5_000.0, max_iterations=3), LogReporter)

    assert "method=bisection" in printed
    assert "mode=capped" in printed
    assert "bracket" in printed
    assert "not available" in printed
    # No relaxed pass is ever run, so no plan on screen is undeliverable.
    assert "mode=relaxed" not in printed


def test_bisection_announces_the_early_exit_rather_than_just_stopping() -> None:
    """A thirteen-pass method finishing in one pass reads as a crash unless it says why."""
    stream = io.StringIO()
    oracle = CycleOracle(
        settlement=_grid(),
        params=ModelParameters.from_spec(SPEC),  # the full 5,000 cycles: never binds
        reporter=LogReporter(stream),
    )

    result = BisectionSearch().search(oracle)

    assert result.passes == 1
    assert "never binds" in stream.getvalue()
    assert "done in 1 pass of a possible 13" in stream.getvalue()


def test_the_recovery_pass_reports_both_of_its_outcomes() -> None:
    """A step that sometimes runs must report the skip too, or its absence reads as a bug."""
    printed = _run(CuttingPlaneSearch(), LogReporter)

    assert "recover" in printed
    assert ("skipped" in printed) or ("not a deliverable plan" in printed)


# -- the cache -----------------------------------------------------------


def test_a_repeated_cycle_value_is_reported_as_cached_not_as_a_free_pass() -> None:
    """The oracle memoises, so a revisited λ costs nothing — and must not look fast."""
    oracle = CycleOracle(settlement=_grid(), params=_params())

    first = oracle.at(0.0, relaxed=True)
    again = oracle.at(0.0, relaxed=True)

    assert again is first
    assert oracle.passes == 1
    assert not oracle.pass_report(first).cached
    assert oracle.pass_report(again).cached


def test_a_pass_records_what_it_cost() -> None:
    """Every estimate the console makes is built on a measured pass duration."""
    oracle = CycleOracle(settlement=_grid(), params=_params())

    point = oracle.at(0.0, relaxed=True)

    assert point.index == 1
    assert point.elapsed > 0.0
    assert oracle.pass_report(point).elapsed == point.elapsed


# -- the renderings ------------------------------------------------------


def test_a_redirected_stream_never_receives_cursor_control() -> None:
    """A carriage return in a log file is noise, so ``auto`` must not emit one."""
    printed = _run(BisectionSearch(upper_bound=5_000.0, max_iterations=2), LogReporter)

    assert "\x1b[" not in printed
    assert "\r" not in printed


def test_the_console_paints_nothing_when_colour_is_declined() -> None:
    """``NO_COLOR`` still gets the live display — unpainted, but still live.

    Cursor control is not colour: the live region is the whole point of this
    rendering, so it keeps redrawing. What goes is the paint.
    """
    stream = io.StringIO()
    reporter = ConsoleReporter(stream, colour=False, unicode=True)
    oracle = CycleOracle(settlement=_grid(), params=_params(), reporter=reporter)

    BisectionSearch(upper_bound=5_000.0, max_iterations=2).search(oracle)
    printed = stream.getvalue()

    assert not re.search(r"\x1b\[[0-9;]*m", printed)  # no colour
    assert "\x1b[J" in printed  # but still a live region
    assert "bisection" in printed


def test_a_terminal_that_cannot_encode_the_drawing_gets_ascii() -> None:
    """A search writes its cells without knowing where they land, so the renderer narrows them."""
    stream = io.StringIO()
    reporter = ConsoleReporter(stream, colour=False, unicode=False)
    oracle = CycleOracle(settlement=_grid(), params=_params(), reporter=reporter)

    BisectionSearch(upper_bound=5_000.0, max_iterations=2).search(oracle)
    printed = stream.getvalue()

    assert printed.isascii()
    assert "lambda" in printed  # the cycle value is still named


def test_json_lines_carry_the_convergence_history() -> None:
    """A sweep should be able to plot a run it did not watch."""
    printed = _run(CuttingPlaneSearch(), JsonReporter)
    events = [json.loads(line) for line in printed.splitlines() if line.strip()]

    finished = [event for event in events if event["event"] == "pass_finished"]
    assert finished
    assert all(event["mode"] in {"relaxed", "capped"} for event in finished)
    assert all(isinstance(event["cycles"], float) for event in finished)
    # The gap is the field a convergence plot is drawn from.
    assert any(event.get("gap") is not None for event in finished)


def test_auto_reads_the_stream_rather_than_being_told() -> None:
    assert isinstance(make_reporter("auto", io.StringIO()), LogReporter)
    assert isinstance(make_reporter("none", io.StringIO()), NullReporter)
    assert isinstance(make_reporter("json", io.StringIO()), JsonReporter)
    assert isinstance(make_reporter("console", io.StringIO()), ConsoleReporter)


def test_an_unknown_progress_mode_names_the_ones_there_are() -> None:
    with pytest.raises(ValueError, match="plain"):
        make_reporter("rainbow", io.StringIO())


def test_the_header_quotes_the_period_length_it_was_given() -> None:
    """A hardcoded "30 min" would state something false the moment ``dt`` changed."""
    stream = io.StringIO()
    plan = RunPlan(
        start=pd.Timestamp("2018-01-01"),
        end=pd.Timestamp("2018-01-02"),
        periods=96,
        period_minutes=15.0,
        windows=2,
        commit_periods=96,
        lookahead_periods=48,
        power_mw=2.0,
        volume_mwh=4.0,
        round_trip_efficiency=0.9025,
        cycle_budget=5_000.0,
        out_path="results/plan.csv",
    )

    ConsoleReporter(stream, colour=False).run_started(plan)
    printed = stream.getvalue()

    assert "96 periods of 15 min" in printed
    # And the window scheme is quoted in hours derived from the same length.
    assert plan.commit_hours == pytest.approx(24.0)
    assert plan.lookahead_hours == pytest.approx(12.0)
    assert "24 h committed + 12 h lookahead" in printed


# -- the estimates -------------------------------------------------------


def test_a_contracting_gap_projects_how_many_passes_are_left() -> None:
    """Halving each pass from 8% to a 1% target is three more passes."""
    assert _passes_to_close([0.16, 0.08], tolerance=0.01) == 3


def test_a_gap_that_is_not_contracting_projects_nothing() -> None:
    """A guess is worse than no guess; the caller falls back on the method's ceiling."""
    assert _passes_to_close([0.08, 0.08], tolerance=0.01) == 0
    assert _passes_to_close([0.08, 0.16], tolerance=0.01) == 0
    assert _passes_to_close([0.08], tolerance=0.01) == 0
    assert _passes_to_close([0.08, 0.004], tolerance=0.01) == 0  # already inside tolerance


def test_durations_read_as_durations() -> None:
    assert _duration(0.42) == "0.4s"
    assert _duration(42.0) == "42s"
    assert _duration(77.0) == "1m 17s"
    assert _duration(4_000.0) == "1h 06m"
