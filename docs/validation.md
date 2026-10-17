# Validation

*What is checked, what checking found, and what a reviewer should still doubt.*

[← README](../README.md) · [data](data.md) · [architecture](architecture.md) ·
[solve](solve.md) · [cycle budget](cycle-budget.md)

---

## How the tests are organized

Each constraint is tested through **the behaviour it exists to produce** rather
than by re-asserting its algebra. Re-stating `S(t) = S(t−1) + …` in a test
proves only that it was typed twice.

`tests/helpers.py::assert_feasible` independently re-derives §4.1 through §4.7
from any schedule. It runs against synthetic shapes, the clock-change week, and
the full three-year output.

```bash
uv run pytest        # 64 tests, ~10 s. The MILP tests need no spreadsheet,
                     # the loader tests need no solver.
```

| File | Tests | Covers |
| --- | --: | --- |
| `test_milp.py` | 11 | Each constraint by the behaviour it produces: flat prices stay idle, a 5% spread is declined against the 0.9025 round trip, a dear Market 2 never tempts a simultaneous buy-and-sell, Market 2 holds flat across the hour while Market 1 moves within it, cycles accrue on discharge only, degradation blocks a refill to nominal |
| `test_rolling.py` | 10 | The handover, the discarded lookahead, one window reproducing the undecomposed solve exactly, and both [cycle-budget](cycle-budget.md) cases, ample and binding |
| `test_grid.py` | 5 | Hourly prices repeated across their pair, the [mislabelled spring hour](data.md#the-quirks-surfaced-and-deliberately-not-repaired) relabelled without reordering prices, whole-hour slicing, mismatched resolutions rejected |
| `test_schedule.py` | 5 | Revenue priced on energy *delivered* not drawn, solver noise reported as zero, §4.7 volumes, empty-schedule summary |
| `test_data_io.py` | 4 | The spec against Attachment 1, both series at their native resolutions, the clock-change artefacts flagged |
| `test_constraints.py` | 13 | Each constraint block against the rows it adds, without a solver: the named rows per period, §4.5 tying only the second half of each hour, the opening state read only in period 0, `DEFAULT_BLOCKS` accounting for every row the assembled model holds, and §4.6's cap left free as a bound so that it can be relaxed |
| `test_pricing.py` | 14 | The two cycle-budget pricers of §6: that a relaxed pass really overspends the budget and a capped one reports no usable slope, that the oracle counts and reuses its passes, the master LP's envelope minimum against cuts whose answer is known on paper, both methods reaching the same schedule, and the dual bound holding above an exactly solved optimum |
| `test_cli.py` | 2 | Both commands end to end, including the written schedule's dates and length |

A strict `mypy` pass and `ruff` run alongside.

## What checking found

**A 1.36 µW artefact.** Verifying the saved three-year schedule against §4.3
failed on one period out of 52,608. The solver had returned a charge variable at
1e-6 MW while discharging, and the zero-cleaning threshold sat at exactly 1e-6.
A MILP is solved to a tolerance, so the threshold is now **10 W**, an order of
magnitude above the solver's feasibility tolerance, with a test for it. Profit
was unchanged to the penny, and the schedule now passes the check with no
post-processing.

**A lost output file.** The first full run printed its results and then died
writing parquet, which needs an engine this project doesn't ship. The default is
CSV now, covered by a CLI test.

Neither was visible in a run that completed and printed plausible numbers.

## Still open

- The value of cycle rationing under the pro-rated budget, over three years.
  Each step re-solves the whole horizon at ~10 minutes a pass, so a calibrated
  three-year run takes hours of compute and does not belong in the test suite.
  It is measured on 7- and 30-day instances with the budget halved, against the
  exact answer.
  ([why it binds there](cycle-budget.md#what-this-means-for-the-actual-answer) ·
  [the measurements](model/cycle-price-experiments.md))
- The dual bound is validated at 30 days, not at 60 or 90. Weak duality needs
  each pass to be a true maximum of the relaxed problem, and a rolling pass with
  one day of lookahead is a heuristic. The bound held above the exact optimum on
  both instances checked, which should be repeated at longer horizons before a
  bound is quoted on the three-year run.
  ([the limits](model/cycle-price-experiments.md#4-limits))
- Foresight is checked on one month, June 2018. A month where the cycle budget
  mattered would test it harder.
  ([the measurement](solve.md#is-one-day-of-foresight-enough))
- There is no heuristic benchmark yet. The `Dispatcher` protocol exists so that
  one can be scored by the same `summarise`, which is the cheapest way to find
  out whether the MILP's complexity is paying for itself.
  ([the seam](architecture.md#modelling-the-decision-section-by-section))

---

Figures from `data/results/dispatch_schedule.csv`, reproduced identically
across two independent full-horizon runs. Formulation:
[`model/model.md`](model/model.md) §1–§7.
