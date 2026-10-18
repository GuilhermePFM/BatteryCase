"""Re-run every measurement the documents quote, in the order they are read.

    uv run python scripts/reproduce_docs.py                 # all of it, ~2 h
    uv run python scripts/reproduce_docs.py --list          # the stages and what they feed
    uv run python scripts/reproduce_docs.py --quick         # the same path, small horizons
    uv run python scripts/reproduce_docs.py dispatch sweep  # named stages only
    uv run python scripts/reproduce_docs.py --dry-run       # print the commands, run nothing

Every number in `README.md`, `docs/model/results.md`,
`docs/model/cycle-value-experiments.md` and `docs/model/tractability.md` comes
from a run, and each of those runs has its own script. This is the one command
that runs them all and says which stage feeds which document, so a claim in the
write-up can be re-derived without first working out what produced it.

Each stage's output is teed to ``data/results/reproduce/<stage>.log`` and the
run finishes with a table of what was produced, what it cost, and where it
landed. Stages are independent except that ``results`` reads the plan
``dispatch`` writes, so they are kept in that order and a failure stops the run
unless ``--keep-going`` is passed.

``--quick`` runs the same stages over short horizons and with short time
limits, writing its CSVs under ``data/results/reproduce/quick/`` rather than
over the committed tables. It checks that the whole path works — it does not
reproduce the figures, which need the horizons the documents quote.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from battery_case.data_io.paths import PROJECT_ROOT, RESULTS_DIR

#: Where logs and the run's summary go.
LOG_DIR = RESULTS_DIR / "reproduce"

#: Where ``--quick`` writes, so a smoke run never overwrites a quoted table.
QUICK_DIR = LOG_DIR / "quick"

#: This interpreter, so a stage inherits the environment ``uv run`` set up
#: rather than nesting another resolution inside it.
PY = sys.executable

#: Window lengths of the table in ``tractability.md``, with the limit each is
#: given. The 60-day row is the one that is expected to stop at its limit; the
#: shorter ones are proved optimal in seconds.
TRACTABILITY_WINDOWS = ((1, 300), (2, 300), (4, 300), (7, 300), (14, 300), (30, 300), (60, 900))

#: The same, trimmed to what a smoke run should spend on it.
QUICK_WINDOWS = ((1, 60), (2, 60), (4, 60))


@dataclass(frozen=True, slots=True)
class Stage:
    """One measurement: the commands that make it, and the claim it supports.

    ``commands`` is a sequence because one row of a table is one solve: the
    window-length table of ``tractability.md`` is seven runs of one script, and
    they are one stage because they produce one table.
    """

    name: str
    feeds: str
    outputs: tuple[str, ...]
    minutes: float
    commands: tuple[tuple[str, ...], ...]
    quick_commands: tuple[tuple[str, ...], ...] = field(default=())

    def for_mode(self, *, quick: bool) -> tuple[tuple[str, ...], ...]:
        return self.quick_commands if quick and self.quick_commands else self.commands


def tractability_commands(
    windows: Sequence[tuple[int, int]], out: Path
) -> tuple[tuple[str, ...], ...]:
    """One one-shot MILP per window length, each recording its row in ``out``."""
    return tuple(
        (PY, "scripts/solve_exact.py", str(days), str(limit), "--csv", str(out))
        for days, limit in windows
    )


QUICK_PLAN = QUICK_DIR / "dispatch_plan.csv"
TRACTABILITY_CSV = PROJECT_ROOT / "docs" / "model" / "tractability.csv"
QUICK_TRACTABILITY_CSV = QUICK_DIR / "tractability.csv"

STAGES: tuple[Stage, ...] = (
    Stage(
        name="figures",
        feeds="model.md §6 — the cutting-plane figure",
        outputs=("docs/model/figures/cutting-plane.png",),
        minutes=0.2,
        commands=((PY, "scripts/plot_cutting_plane.py"),),
    ),
    Stage(
        name="tests",
        feeds="validation.md, and the two subproblem tables of cycle-value-experiments.md §1",
        outputs=("stdout",),
        minutes=0.5,
        commands=((PY, "-m", "pytest", "-q"),),
    ),
    Stage(
        name="dispatch",
        feeds="results.md §7, and the £207,365 of tractability.md",
        outputs=("data/results/dispatch_plan.csv",),
        minutes=13.0,
        commands=((PY, "-m", "battery_case.cli", "dispatch", "--progress", "plain"),),
        quick_commands=(
            (
                PY,
                "-m",
                "battery_case.cli",
                "dispatch",
                "--progress",
                "plain",
                "--start",
                "2018-01-01",
                "--end",
                "2018-01-31",
                "--out",
                str(QUICK_PLAN),
            ),
        ),
    ),
    Stage(
        name="results",
        feeds="results.md — the market split, the year table, the yardstick, the capex context",
        outputs=("stdout",),
        minutes=0.2,
        commands=((PY, "scripts/results_figures.py"),),
        quick_commands=((PY, "scripts/results_figures.py", str(QUICK_PLAN)),),
    ),
    Stage(
        name="sweep",
        feeds="cycle-value-experiments.md §2 — both methods against an exact solve, 1 to 90 days",
        outputs=("docs/model/cycle-value-sweep.csv",),
        minutes=4.0,
        commands=((PY, "scripts/sweep_searches.py"),),
        quick_commands=(
            (
                PY,
                "scripts/sweep_searches.py",
                "1",
                "2",
                "4",
                "7",
                "--out",
                str(QUICK_DIR / "cycle-value-sweep.csv"),
            ),
        ),
    ),
    Stage(
        name="tolerance",
        feeds="cycle-value-experiments.md §2 — what the tolerance buys, on the 30-day instance",
        outputs=("docs/model/cycle-value-tolerance.csv",),
        minutes=1.0,
        commands=((PY, "scripts/tolerance_sweep.py", "30"),),
        quick_commands=(
            (
                PY,
                "scripts/tolerance_sweep.py",
                "7",
                "--out",
                str(QUICK_DIR / "cycle-value-tolerance.csv"),
            ),
        ),
    ),
    Stage(
        name="long-horizons",
        feeds="cycle-value-experiments.md §2 — cutting planes at 180, 365 and 1,096 days",
        outputs=("docs/model/cycle-value-long-horizons.csv",),
        minutes=17.0,
        commands=(
            (
                PY,
                "scripts/sweep_searches.py",
                "180",
                "365",
                "all",
                "--search",
                "cutting-plane",
                "--no-exact",
                "--out",
                "cycle-value-long-horizons.csv",
            ),
        ),
        quick_commands=(
            (
                PY,
                "scripts/sweep_searches.py",
                "14",
                "--search",
                "cutting-plane",
                "--no-exact",
                "--out",
                str(QUICK_DIR / "cycle-value-long-horizons.csv"),
            ),
        ),
    ),
    Stage(
        name="tractability",
        feeds="tractability.md — solve time against window length",
        outputs=("docs/model/tractability.csv",),
        minutes=20.0,
        commands=tractability_commands(TRACTABILITY_WINDOWS, TRACTABILITY_CSV),
        quick_commands=tractability_commands(QUICK_WINDOWS, QUICK_TRACTABILITY_CSV),
    ),
    Stage(
        name="monolith",
        feeds="tractability.md — the whole horizon as one MILP, given an hour",
        outputs=("docs/model/tractability.csv",),
        minutes=60.0,
        commands=((PY, "scripts/solve_exact.py", "0", "3600", "--csv", str(TRACTABILITY_CSV)),),
        quick_commands=(
            (PY, "scripts/solve_exact.py", "0", "120", "--csv", str(QUICK_TRACTABILITY_CSV)),
        ),
    ),
)

BY_NAME = {stage.name: stage for stage in STAGES}


@dataclass(frozen=True, slots=True)
class Options:
    stages: tuple[Stage, ...]
    quick: bool
    dry_run: bool
    keep_going: bool


def parse_args(argv: Sequence[str]) -> Options:
    """The stages to run and how, or exit with the list of names on a typo."""
    names: list[str] = []
    quick = dry_run = keep_going = False

    for argument in argv:
        if argument == "--quick":
            quick = True
        elif argument == "--dry-run":
            dry_run = True
        elif argument == "--keep-going":
            keep_going = True
        elif argument == "--list":
            print_stages()
            raise SystemExit(0)
        elif argument.startswith("-"):
            raise SystemExit(f"unknown option {argument}; see --list and the module docstring")
        else:
            names.append(argument)

    unknown = [name for name in names if name not in BY_NAME]
    if unknown:
        raise SystemExit(f"unknown stage(s): {', '.join(unknown)}\nhave: {', '.join(BY_NAME)}")

    chosen = tuple(BY_NAME[name] for name in names) if names else STAGES
    return Options(stages=chosen, quick=quick, dry_run=dry_run, keep_going=keep_going)


def print_stages() -> None:
    """The catalogue: every stage, what it feeds, and what it costs."""
    print(f"{'stage':<15}{'~min':>7}  feeds")
    print("-" * 96)
    for stage in STAGES:
        print(f"{stage.name:<15}{stage.minutes:>7.1f}  {stage.feeds}")
    print("-" * 96)
    print(f"{'total':<15}{sum(stage.minutes for stage in STAGES):>7.1f}")


def run_stage(stage: Stage, options: Options) -> tuple[str, float]:
    """Run one stage, teeing its output to its log. Returns the status and cost."""
    commands = stage.for_mode(quick=options.quick)
    log = LOG_DIR / f"{stage.name}.log"
    started = time.perf_counter()

    print(f"\n=== {stage.name}  ({len(commands)} command(s), ~{stage.minutes:.0f} min)")
    print(f"    feeds  {stage.feeds}")
    for command in commands:
        print(f"    $ {' '.join(command)}")
    if options.dry_run:
        return "dry-run", 0.0

    with log.open("w") as handle:
        handle.write(f"# {stage.name}: {stage.feeds}\n")
        for command in commands:
            handle.write(f"\n$ {' '.join(command)}\n")
            handle.flush()
            # Output goes to the log and to this terminal, so a two-hour run is
            # watchable and still leaves a record of every figure it printed.
            # Unbuffered, or a stage's own progress would arrive in bursts —
            # which HiGHS's solver log does anyway, being written from C++.
            process = subprocess.Popen(
                command,
                cwd=PROJECT_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            assert process.stdout is not None
            for line in process.stdout:
                sys.stdout.write(f"    {line}")
                handle.write(line)
            if process.wait() != 0:
                return f"failed ({process.returncode})", time.perf_counter() - started

    return "ok", time.perf_counter() - started


def main(argv: Sequence[str]) -> int:
    options = parse_args(argv)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if options.quick:
        QUICK_DIR.mkdir(parents=True, exist_ok=True)

    estimate = sum(stage.minutes for stage in options.stages)
    print(f"reproducing {len(options.stages)} stage(s)" + (" (quick)" if options.quick else ""))
    print(f"logs in {LOG_DIR}" + (f", CSVs in {QUICK_DIR}" if options.quick else ""))
    if not options.quick and not options.dry_run:
        print(f"estimated {estimate:.0f} min on the machine the documents were measured on")

    outcomes: list[tuple[Stage, str, float]] = []
    for stage in options.stages:
        status, seconds = run_stage(stage, options)
        outcomes.append((stage, status, seconds))
        if status.startswith("failed") and not options.keep_going:
            print(f"\n{stage.name} failed; stopping (pass --keep-going to carry on)")
            break

    print(f"\n{'stage':<15}{'status':>12}{'minutes':>10}  outputs")
    print("-" * 80)
    for stage, status, seconds in outcomes:
        print(f"{stage.name:<15}{status:>12}{seconds / 60:>10.1f}  {', '.join(stage.outputs)}")

    failed = [stage.name for stage, status, _ in outcomes if status.startswith("failed")]
    skipped = len(options.stages) - len(outcomes)
    if skipped:
        print(f"\n{skipped} stage(s) not run")
    if failed:
        print(f"\nfailed: {', '.join(failed)} — see {LOG_DIR}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
