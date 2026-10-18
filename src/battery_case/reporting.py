"""CLI reporting.

A calibrated dispatch is a loop of loops: a search spends *passes*, and each
pass walks the horizon *window* by window.

The modelling code should not know what a terminal is, so what it emits is
*events*: a run started, a pass started, a window committed, a pass finished.
:class:`Reporter` is the seam, exactly as
:class:`~battery_case.modelling.cycle_value.oracle.DualSearch` is the seam for
the method itself, and the default is :class:`NullReporter` so a test or a
notebook runs silent without arranging anything.

Four renderings sit behind that seam, chosen by :func:`make_reporter`:

* :class:`ConsoleReporter` for a terminal — committed history scrolls, one
  live region redraws. This is the whole design rule: a finished pass becomes
  static text, and only the pass in flight moves.
* :class:`LogReporter` for a pipe or a CI job, where a carriage return is
  noise: one timestamped line per event.
* :class:`JsonReporter` for a sweep script that wants the convergence history
  back without re-running anything.
* :class:`NullReporter`, the default.

The table a search fills is split in two. The columns every method shares —
pass, cycle value, cycles, overspend, profit — belong to this module, because
they come off a :class:`~battery_case.modelling.cycle_value.oracle.DualPoint`
whatever found it. The columns that differ belong to the search, which declares
them in a :class:`SearchPlan` and fills them per pass, so a renderer can lay out
cutting planes and bisection without knowing how either method works.
"""

from __future__ import annotations

import json
import math
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import IO, Literal, Protocol

import pandas as pd

from battery_case.modelling.rolling_horizon import WindowProgress

#: How often the live region may redraw, in seconds. Fast enough to look live,
#: slow enough that the terminal is not the bottleneck on a short window.
REDRAW_INTERVAL = 0.1

#: State of a phase, which is what the leading glyph encodes.
PhaseState = Literal["running", "done", "warned", "failed"]

_GLYPHS: dict[PhaseState, tuple[str, str]] = {
    "running": ("▸", "cyan"),
    "done": ("✓", "green"),
    "warned": ("!", "amber"),
    "failed": ("✗", "red"),
}

_ASCII_GLYPHS: dict[PhaseState, str] = {
    "running": ">",
    "done": "ok",
    "warned": "!",
    "failed": "x",
}

#: What a terminal that cannot encode the box drawing gets instead. A search
#: writes its cells without knowing where they will be shown, so narrowing them
#: is the renderer's job and happens once, on the way out.
_PLAIN = {
    "\u2713": "ok",
    "\u2717": "x",
    "\u03bb": "lambda",
    "\u00b7": ".",
    "\u2014": "-",
    "\u2212": "-",
    "\u2265": ">=",
    "\u2264": "<=",
    "\u2260": "!=",
    "\u2208": "in",
    "\u2192": "->",
    "\u00d7": "x",
    "\u2500": "-",
    "\u00a3": "GBP",
    "\u2026": "...",
}

_SGR = {
    "dim": "2",
    "bold": "1",
    "green": "32",
    "cyan": "36",
    "amber": "33",
    "red": "31",
    "white": "1;37",
}


@dataclass(frozen=True, slots=True)
class RunPlan:
    """What the run intends to do, known before the first window is solved.

    Printing this is what lets a reader decide whether to wait: it carries the
    horizon, the battery, the window scheme and where the plan will be written.
    """

    start: pd.Timestamp
    end: pd.Timestamp
    periods: int
    period_minutes: float
    windows: int
    commit_periods: int
    lookahead_periods: int
    power_mw: float
    volume_mwh: float
    round_trip_efficiency: float
    cycle_budget: float
    out_path: str

    @property
    def commit_hours(self) -> float:
        """The committed part of a window, in hours rather than in periods."""
        return self.commit_periods * self.period_minutes / 60.0

    @property
    def lookahead_hours(self) -> float:
        """The part of a window that is solved and then discarded, in hours."""
        return self.lookahead_periods * self.period_minutes / 60.0


@dataclass(frozen=True, slots=True)
class Column:
    """One method-specific column of the pass table."""

    header: str
    width: int


@dataclass(frozen=True, slots=True)
class SearchPlan:
    """What a method costs and which columns it fills.

    ``passes_known`` is the difference the two methods make to the display, not
    a detail: bisection spends ``1 + max_iterations`` passes whatever the data,
    so the run bar is a measurement, while cutting planes stop on a gap and
    every pass estimate is a guess that must be marked as one.
    """

    method: str
    detail: str
    max_passes: int
    passes_known: bool
    columns: tuple[Column, ...] = ()
    tolerance: float | None = None


@dataclass(frozen=True, slots=True)
class PassReport:
    """One finished pass, in the terms every method shares.

    ``gap`` is the method's own convergence measure where it has one, and is
    the only field here a renderer may use to guess how many passes are left.
    """

    index: int
    cycle_value: float
    relaxed: bool
    profit: float
    cycles: float
    budget: float
    lagrangian: float
    subgradient: float
    within_budget: bool
    elapsed: float
    cached: bool = False
    recovery: bool = False
    gap: float | None = None

    @property
    def overspend(self) -> float:
        """Cycles spent as a fraction over the budget; negative when under."""
        return self.cycles / self.budget - 1.0 if self.budget else 0.0

    @property
    def mode(self) -> str:
        return "relaxed" if self.relaxed else "capped"


class Reporter(Protocol):
    """Somewhere for a run to say what it is doing."""

    def run_started(self, plan: RunPlan) -> None: ...

    def phase(
        self,
        name: str,
        state: PhaseState,
        detail: str = "",
        elapsed: float | None = None,
    ) -> None: ...

    def search_started(self, plan: SearchPlan) -> None: ...

    def pass_started(
        self, index: int, cycle_value: float, *, relaxed: bool, label: str
    ) -> None: ...

    def window_done(self, progress: WindowProgress) -> None: ...

    def pass_finished(self, report: PassReport, cells: Sequence[str] = ()) -> None: ...

    def note(self, text: str) -> None: ...

    def interrupted(self, lines: Sequence[str]) -> None: ...

    def failed(self, title: str, lines: Sequence[str]) -> None: ...

    def run_finished(self, elapsed: float, passes: int) -> None: ...


class NullReporter:
    """Say nothing. The default, so nothing has to opt out of being quiet."""

    def run_started(self, plan: RunPlan) -> None:
        return None

    def phase(
        self,
        name: str,
        state: PhaseState,
        detail: str = "",
        elapsed: float | None = None,
    ) -> None:
        return None

    def search_started(self, plan: SearchPlan) -> None:
        return None

    def pass_started(self, index: int, cycle_value: float, *, relaxed: bool, label: str) -> None:
        return None

    def window_done(self, progress: WindowProgress) -> None:
        return None

    def pass_finished(self, report: PassReport, cells: Sequence[str] = ()) -> None:
        return None

    def note(self, text: str) -> None:
        return None

    def interrupted(self, lines: Sequence[str]) -> None:
        return None

    def failed(self, title: str, lines: Sequence[str]) -> None:
        return None

    def run_finished(self, elapsed: float, passes: int) -> None:
        return None


#: The shared columns, which come off a ``DualPoint`` whatever method found it.
SHARED_COLUMNS = (
    Column("pass", 4),
    Column("λ £/cyc", 8),
    Column("cycles", 9),
    Column("vs budget", 9),
    Column("profit £", 12),
)


class ConsoleReporter(NullReporter):
    """Draw the run in a terminal: history above, one live region below.

    The live region is the only thing that redraws, so scrollback holds the
    whole convergence history and the reader can look away and come back.
    """

    def __init__(
        self,
        stream: IO[str] | None = None,
        *,
        colour: bool = True,
        unicode: bool = True,
    ) -> None:
        self._out = stream if stream is not None else sys.stderr
        self._colour = colour
        self._unicode = unicode
        self._live = 0
        self._last_draw = 0.0

        self._search: SearchPlan | None = None
        self._pass: tuple[int, float, bool, str] | None = None
        self._pass_started = 0.0
        self._progress: WindowProgress | None = None
        self._durations: list[float] = []
        self._gaps: list[float] = []

    # -- plumbing ---------------------------------------------------------

    def _paint(self, text: str, tone: str) -> str:
        return f"\x1b[{_SGR[tone]}m{text}\x1b[0m" if self._colour else text

    def _line(self, text: str) -> str:
        """Narrow a line to ASCII when the terminal cannot encode it."""
        if self._unicode:
            return text
        for fancy, plain in _PLAIN.items():
            text = text.replace(fancy, plain)
        return text

    def _erase(self) -> None:
        if self._live:
            self._out.write(f"\x1b[{self._live}A\x1b[J")
            self._live = 0

    def _commit(self, *lines: str) -> None:
        """Write lines that stay on screen for the rest of the run."""
        self._erase()
        for line in lines:
            self._out.write(self._line(line) + "\n")
        self._out.flush()

    def _draw(self, lines: Sequence[str], *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_draw < REDRAW_INTERVAL:
            return
        self._erase()
        for line in lines:
            self._out.write(self._line(line) + "\n")
        self._live = len(lines)
        self._last_draw = now
        self._out.flush()

    def _glyph(self, state: PhaseState) -> str:
        if not self._unicode:
            return self._paint(f"{_ASCII_GLYPHS[state]:<2}", _GLYPHS[state][1])
        mark, tone = _GLYPHS[state]
        return self._paint(f"{mark:<2}", tone)

    def _bar(self, fraction: float, width: int = 40) -> str:
        filled = max(0, min(width, round(fraction * width)))
        if not self._unicode:
            return self._paint("=" * filled, "cyan") + "-" * (width - filled)
        return self._paint("▌" * filled, "cyan") + self._paint(
            "░" * (width - filled), "dim"
        )

    # -- events -----------------------------------------------------------

    def run_started(self, plan: RunPlan) -> None:
        rule = "─" * 71 if self._unicode else "-" * 71
        arrow = "→" if self._unicode else "->"
        self._commit(
            "",
            self._paint("battery-case · dispatch", "white"),
            self._paint(rule, "dim"),
            self._field(
                "horizon",
                f"{plan.start:%Y-%m-%d} {arrow} {plan.end:%Y-%m-%d}   "
                f"{plan.periods:,} periods of {plan.period_minutes:g} min",
            ),
            self._field(
                "battery",
                f"{plan.volume_mwh:,.1f} MWh \u00b7 {plan.power_mw:,.1f} MW "
                f"\u00b7 {plan.round_trip_efficiency:.1%} round-trip "
                f"\u00b7 {plan.cycle_budget:,.0f} cycles",
            ),
            self._field(
                "windows",
                f"{plan.windows:,}, each {plan.commit_hours:g} h committed "
                f"+ {plan.lookahead_hours:g} h lookahead",
            ),
            self._field("output", plan.out_path),
            self._paint(rule, "dim"),
            "",
        )

    def _field(self, name: str, value: str) -> str:
        return f"  {self._paint(f'{name:<9}', 'dim')} {value}"

    def phase(
        self,
        name: str,
        state: PhaseState,
        detail: str = "",
        elapsed: float | None = None,
    ) -> None:
        line = f"  {self._glyph(state)} {self._paint(_pad(name), 'white')} {detail}"
        if elapsed is not None:
            line = f"{line}  {self._paint(_duration(elapsed), 'dim')}"
        if state == "running":
            self._draw([line.rstrip()], force=True)
            self._live = 0  # the phase line stays; the table will follow it
            self._out.write("")
        else:
            self._commit(line.rstrip())

    def search_started(self, plan: SearchPlan) -> None:
        self._search = plan
        columns = (*SHARED_COLUMNS, *plan.columns)
        header = "   " + "  ".join(f"{c.header:>{c.width}}" for c in columns)
        rule = "   " + "  ".join(
            ("─" if self._unicode else "-") * c.width for c in columns
        )
        self._commit("", self._paint(header, "dim"), self._paint(rule, "dim"))

    def pass_started(self, index: int, cycle_value: float, *, relaxed: bool, label: str) -> None:
        self._pass = (index, cycle_value, relaxed, label)
        self._pass_started = time.monotonic()
        self._progress = None
        self._redraw(force=True)

    def window_done(self, progress: WindowProgress) -> None:
        self._progress = progress
        self._redraw()

    def pass_finished(self, report: PassReport, cells: Sequence[str] = ()) -> None:
        self._erase()
        self._pass = None
        self._progress = None
        if report.gap is not None:
            self._gaps.append(report.gap)
        if not report.cached:
            self._durations.append(report.elapsed)
        self._commit(self._row(report, cells))

    def note(self, text: str) -> None:
        self._commit(self._paint(f"        {text}", "dim"))

    def interrupted(self, lines: Sequence[str]) -> None:
        self._erase()
        self._commit(
            "",
            f"  {self._glyph('warned')} {self._paint('stopped', 'white')}    {lines[0]}",
            *(self._paint(f"       {line}", "dim") for line in lines[1:]),
        )

    def failed(self, title: str, lines: Sequence[str]) -> None:
        self._erase()
        self._commit(
            "",
            f"  {self._glyph('failed')} {self._paint('failed', 'white')}     {title}",
            *(self._paint(f"       {line}", "dim") for line in lines),
        )

    def run_finished(self, elapsed: float, passes: int) -> None:
        self._erase()
        self._commit(
            # Pad before painting: escape codes have no width, but str.format
            # counts them, so a painted label padded afterwards comes out short.
            f"  {self._glyph('done')} {self._paint(_pad('done'), 'white')} "
            f"{_duration(elapsed)} · {passes_phrase(passes)}",
            "",
        )

    # -- the live region --------------------------------------------------

    def _row(self, report: PassReport, cells: Sequence[str]) -> str:
        widths = [c.width for c in SHARED_COLUMNS]
        over = f"{report.overspend:+.1%}"
        tone = "green" if report.within_budget else "red"
        parts = [
            f"{report.index:>{widths[0]}}",
            f"{report.cycle_value:>{widths[1]},.2f}",
            f"{report.cycles:>{widths[2]},.1f}",
            self._paint(f"{over:>{widths[3]}}", tone),
            f"{report.profit:>{widths[4]},.0f}",
        ]
        extras = self._search.columns if self._search else ()
        for column, cell in zip(extras, cells, strict=False):
            parts.append(f"{cell:>{column.width}}")
        suffix = ""
        if report.cached:
            suffix = self._paint("  cached", "dim")
        elif report.recovery:
            suffix = self._paint("  recovered", "green")
        return "   " + "  ".join(parts) + suffix

    def _redraw(self, *, force: bool = False) -> None:
        if self._pass is None:
            return
        index, cycle_value, relaxed, label = self._pass
        head = (
            f"   {self._paint(f'{index:>4}', 'cyan')}  {cycle_value:>8,.2f}  "
            + "  ".join(f"{'·' if self._unicode else '.':>{c.width}}"
                        for c in SHARED_COLUMNS[2:])
        )
        mode = label or ("relaxed" if relaxed else "capped")
        head = f"{head}  {self._paint(mode, 'amber' if relaxed else 'green')}"

        lines = [head]
        progress = self._progress
        if progress is None:
            lines.append("     " + self._paint("solving the first window …", "dim"))
        else:
            spent = max(time.monotonic() - self._pass_started, 1e-6)
            rate = progress.window / spent
            left = (progress.windows - progress.window) / rate if rate else 0.0
            lines.append(
                f"     {self._bar(progress.fraction)}  {progress.fraction:>4.0%}  "
                f"{progress.window:,}/{progress.windows:,} windows"
            )
            lines.append(
                "     "
                + self._paint(
                    f"at {progress.at:%Y-%m-%d} · {rate:,.1f} win/s "
                    f"· {_duration(spent)} elapsed · ~{_duration(left)} left",
                    "dim",
                )
            )
            footer = self._run_footer(index)
            if footer:
                lines.append("     " + self._paint(footer, "dim"))
        self._draw(lines, force=force)

    def _run_footer(self, index: int) -> str:
        """How much of the *run* is left — exact for bisection, a guess otherwise."""
        plan = self._search
        if plan is None or not self._durations:
            return ""
        mean = sum(self._durations) / len(self._durations)
        left = self._passes_left(index)
        if left is None:
            return f"pass {index} · passes remaining unknown"
        total = index + left
        if plan.passes_known:
            return (
                f"pass {index} of {total} · "
                f"~{_duration(left * mean)} left in the run"
            )
        return (
            f"pass {index} · ~{left} more pass(es) expected "
            f"· ~{_duration(left * mean)} left in the run"
        )

    def _passes_left(self, index: int) -> int | None:
        plan = self._search
        if plan is None:
            return None
        ceiling = max(plan.max_passes - index, 0)
        if plan.passes_known:
            return ceiling
        return min(_passes_to_close(self._gaps, plan.tolerance), ceiling)


def _passes_to_close(gaps: Sequence[float], tolerance: float | None) -> int:
    """Project how many more passes a gap contracting at its observed rate needs.

    Two gaps give a ratio, the ratio gives a geometric projection, and anything
    that is not contracting gives no answer at all — in which case the caller
    falls back on the method's own pass ceiling.
    """
    usable = [gap for gap in gaps if gap > 0.0]
    if tolerance is None or len(usable) < 2 or usable[-1] <= tolerance:
        return 0
    ratio = usable[-1] / usable[-2]
    if not 0.0 < ratio < 1.0:
        return 0
    return max(1, math.ceil(math.log(tolerance / usable[-1]) / math.log(ratio)))


class LogReporter(NullReporter):
    """One timestamped line per event, for a pipe, a log file or CI.

    No cursor control and no box drawing, because neither survives a redirect,
    and progress is thinned to quarters so a three-year run does not write a
    thousand lines of percentage.
    """

    #: Progress is logged at these fractions of a pass, and nowhere else.
    MARKS = (0.25, 0.5, 0.75)

    def __init__(self, stream: IO[str] | None = None) -> None:
        self._out = stream if stream is not None else sys.stderr
        self._marks: set[float] = set()

    def _say(self, kind: str, text: str) -> None:
        self._out.write(f"{time.strftime('%H:%M:%S')} {kind:<8} {text}\n")
        self._out.flush()

    def run_started(self, plan: RunPlan) -> None:
        self._say(
            "start",
            f"horizon={plan.start:%Y-%m-%d}/{plan.end:%Y-%m-%d} periods={plan.periods} "
            f"period_minutes={plan.period_minutes:g} windows={plan.windows} "
            f"budget={plan.cycle_budget:g} out={plan.out_path}",
        )

    def phase(
        self,
        name: str,
        state: PhaseState,
        detail: str = "",
        elapsed: float | None = None,
    ) -> None:
        suffix = "" if elapsed is None else f" elapsed={elapsed:.1f}s"
        self._say(name, f"{state} {detail}".strip() + suffix)

    def search_started(self, plan: SearchPlan) -> None:
        self._say(
            "search",
            f"method={plan.method} max_passes={plan.max_passes} "
            f"passes_known={plan.passes_known} tolerance={plan.tolerance}",
        )

    def pass_started(self, index: int, cycle_value: float, *, relaxed: bool, label: str) -> None:
        self._marks = set()
        mode = "relaxed" if relaxed else "capped"
        extra = f" {label}" if label else ""
        self._say(f"pass {index}", f"begin lambda={cycle_value:.4f} mode={mode}{extra}")

    def window_done(self, progress: WindowProgress) -> None:
        for mark in self.MARKS:
            if progress.fraction >= mark and mark not in self._marks:
                self._marks.add(mark)
                self._say(
                    "progress",
                    f"windows={progress.window}/{progress.windows} {mark:.0%} at {progress.at}",
                )

    def pass_finished(self, report: PassReport, cells: Sequence[str] = ()) -> None:
        gap = "n/a" if report.gap is None else f"{report.gap:.6f}"
        self._say(
            f"pass {report.index}",
            f"end lambda={report.cycle_value:.4f} profit={report.profit:.2f} "
            f"cycles={report.cycles:.1f} L={report.lagrangian:.2f} "
            f"subgradient={report.subgradient:.1f} gap={gap} "
            f"within_budget={report.within_budget} cached={report.cached} "
            f"elapsed={report.elapsed:.1f}s",
        )

    def note(self, text: str) -> None:
        self._say("note", text)

    def interrupted(self, lines: Sequence[str]) -> None:
        for line in lines:
            self._say("stopped", line)

    def failed(self, title: str, lines: Sequence[str]) -> None:
        self._say("failed", title)
        for line in lines:
            self._say("failed", line)

    def run_finished(self, elapsed: float, passes: int) -> None:
        self._say("done", f"passes={passes} elapsed={elapsed:.1f}s")


class JsonReporter(NullReporter):
    """One JSON object per line, so a sweep can plot a run it did not watch."""

    def __init__(self, stream: IO[str] | None = None) -> None:
        self._out = stream if stream is not None else sys.stderr

    def _emit(self, event: str, **fields: object) -> None:
        self._out.write(json.dumps({"event": event, **fields}) + "\n")
        self._out.flush()

    def run_started(self, plan: RunPlan) -> None:
        self._emit(
            "run_started",
            start=f"{plan.start:%Y-%m-%d}",
            end=f"{plan.end:%Y-%m-%d}",
            periods=plan.periods,
            period_minutes=plan.period_minutes,
            windows=plan.windows,
            budget=plan.cycle_budget,
        )

    def phase(
        self,
        name: str,
        state: PhaseState,
        detail: str = "",
        elapsed: float | None = None,
    ) -> None:
        self._emit("phase", name=name, state=state, detail=detail, elapsed=elapsed)

    def search_started(self, plan: SearchPlan) -> None:
        self._emit(
            "search_started",
            method=plan.method,
            max_passes=plan.max_passes,
            passes_known=plan.passes_known,
            tolerance=plan.tolerance,
        )

    def pass_started(self, index: int, cycle_value: float, *, relaxed: bool, label: str) -> None:
        self._emit("pass_started", index=index, cycle_value=cycle_value, relaxed=relaxed)

    def window_done(self, progress: WindowProgress) -> None:
        if progress.window % 100 == 0 or progress.window == progress.windows:
            self._emit("window", window=progress.window, windows=progress.windows)

    def pass_finished(self, report: PassReport, cells: Sequence[str] = ()) -> None:
        self._emit(
            "pass_finished",
            index=report.index,
            cycle_value=report.cycle_value,
            mode=report.mode,
            profit=report.profit,
            cycles=report.cycles,
            lagrangian=report.lagrangian,
            subgradient=report.subgradient,
            within_budget=report.within_budget,
            gap=report.gap,
            cached=report.cached,
            recovery=report.recovery,
            elapsed=report.elapsed,
        )

    def note(self, text: str) -> None:
        self._emit("note", text=text)

    def interrupted(self, lines: Sequence[str]) -> None:
        self._emit("interrupted", lines=list(lines))

    def failed(self, title: str, lines: Sequence[str]) -> None:
        self._emit("failed", title=title, lines=list(lines))

    def run_finished(self, elapsed: float, passes: int) -> None:
        self._emit("run_finished", elapsed=elapsed, passes=passes)


#: The renderings ``--progress`` chooses between. ``auto`` reads the terminal.
PROGRESS_MODES = ("auto", "console", "plain", "json", "none")


def make_reporter(mode: str = "auto", stream: IO[str] | None = None) -> Reporter:
    """Build the rendering ``mode`` asks for, reading the terminal when it says ``auto``.

    ``auto`` is the only mode that inspects anything: a redirected stream gets
    line logs, because a carriage return in a log file is noise, and a terminal
    that has asked for no colour (``NO_COLOR``) or cannot encode box drawing
    still gets the live display, in ASCII and unpainted.
    """
    import os

    out = stream if stream is not None else sys.stderr
    if mode == "none":
        return NullReporter()
    if mode == "json":
        return JsonReporter(out)
    if mode == "plain":
        return LogReporter(out)
    if mode == "console":
        return ConsoleReporter(out, colour=_wants_colour(out), unicode=_wants_unicode(out))
    if mode != "auto":
        raise ValueError(f"unknown progress mode {mode!r}; available: {', '.join(PROGRESS_MODES)}")

    interactive = bool(getattr(out, "isatty", lambda: False)()) and not os.environ.get("CI")
    if not interactive:
        return LogReporter(out)
    return ConsoleReporter(out, colour=_wants_colour(out), unicode=_wants_unicode(out))


def _wants_colour(stream: IO[str]) -> bool:
    import os

    if os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


def _wants_unicode(stream: IO[str]) -> bool:
    encoding = (getattr(stream, "encoding", "") or "").lower()
    return "utf" in encoding


#: Width of the phase-name column, so every phase line starts in the same place.
PHASE_WIDTH = 10


def _pad(name: str) -> str:
    return f"{name:<{PHASE_WIDTH}}"


def passes_phrase(count: int) -> str:
    """``1 pass`` / ``6 passes`` — output that reads as written, not as generated."""
    return f"{count} pass" if count == 1 else f"{count} passes"


def _duration(seconds: float) -> str:
    """A duration a reader can hold in their head: ``0.4s``, ``1m 17s``, ``1h 06m``."""
    if seconds < 10:
        return f"{seconds:.1f}s"
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{int(seconds) // 60}m {int(seconds) % 60:02d}s"
    return f"{int(seconds) // 3600}h {(int(seconds) % 3600) // 60:02d}m"
