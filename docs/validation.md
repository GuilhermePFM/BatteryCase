# Validation

*What is checked, what checking found, and what a reviewer should still doubt.*

[← README](../README.md) · [data](data.md) · [architecture](architecture.md) ·
[solve](solve.md) · [cycle budget](cycle-budget.md)

---

## How the tests are organized

The 37 tests are organized so that each constraint is tested by **the behaviour
it exists to produce**, not by re-asserting its algebra. Re-stating `S(t) =
S(t−1) + …` in a test proves only that it was typed twice.

`tests/helpers.py::assert_feasible` independently re-derives §4.1 through §4.7
from any schedule, and is run against synthetic shapes, the clock-change week,
and the full three-year output.

```bash
uv run pytest        # 37 tests, ~6 s — no spreadsheet needed for the MILP tests,
                     # no solver needed for the loader tests
```

| File | Tests | Covers |
| --- | --: | --- |
| `test_milp.py` | 11 | Each constraint by the behaviour it produces: flat prices stay idle, a 5% spread is declined against the 0.9025 round trip, a dear Market 2 never tempts a simultaneous buy-and-sell, Market 2 holds flat across the hour while Market 1 moves within it, cycles accrue on discharge only, degradation blocks a refill to nominal |
| `test_rolling.py` | 10 | The handover, the discarded lookahead, one window reproducing the undecomposed solve exactly, and both [cycle-budget](cycle-budget.md) cases — ample and binding |
| `test_grid.py` | 5 | Hourly prices repeated across their pair, the [mislabelled spring hour](data.md#the-quirks-surfaced-and-deliberately-not-repaired) relabelled without reordering prices, whole-hour slicing, mismatched resolutions rejected |
| `test_schedule.py` | 5 | Revenue priced on energy *delivered* not drawn, solver noise reported as zero, §4.7 volumes, empty-schedule summary |
| `test_data_io.py` | 4 | The spec against Attachment 1, both series at their native resolutions, the clock-change artefacts flagged |
| `test_cli.py` | 2 | Both commands end to end, including the written schedule's dates and length |

A strict `mypy` pass and `ruff` run alongside.

## Two things found by checking rather than by thinking

**A 1.36 µW artefact.** Verifying the saved three-year schedule against §4.3
failed on one period out of 52,608: the solver returned a charge variable at
1e-6 MW while discharging, and the zero-cleaning threshold sat at exactly 1e-6.
A MILP is solved to a tolerance, not exactly, so the threshold is now **10 W**
— an order of magnitude above the solver's feasibility tolerance — with a test
for it. Profit was unchanged to the penny; the schedule now passes the check
with no post-processing.

**A lost output file.** The first full run printed its results and then died
writing parquet, which needs an engine this project doesn't ship. The default
is CSV now, covered by a CLI test.

Both are the same lesson in different clothes: the run that *looks* finished is
not the run that has been checked.

## Still open

- **The value of cycle rationing under the pro-rated budget.** The one number
  the implementation can produce but hasn't — each bisection step re-solves the
  whole horizon at ~12 minutes a pass, so a calibrated three-year run is a
  couple of hours of compute, not a test-suite item.
  ([why it binds there](cycle-budget.md#what-this-means-for-the-actual-answer))
- **Foresight is checked on one month** (June 2018). A month where the cycle
  budget mattered would test it harder.
  ([the measurement](solve.md#is-one-day-of-foresight-enough))
- **No heuristic benchmark yet.** The `Dispatcher` protocol exists so one can be
  scored by the same `summarise` — the cheapest way to find out whether the MILP
  is earning its complexity.
  ([the seam](architecture.md#modelling--the-decision-section-by-section))

---

Figures from `data/results/dispatch_schedule.csv`, reproduced identically
across two independent full-horizon runs. Formulation:
[`model/model.md`](model/model.md) §1–§7.
