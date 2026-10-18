# Validation

*What is checked, what the checks pin down, and what a reviewer should still doubt.*

[← README](../README.md) · [data](data.md) · [architecture](architecture.md) ·
[solve](solve.md) · [cycle budget](cycle-budget.md) ·
[glossary](glossary.md)

---

## How the tests are organized

Each constraint is tested through **the behaviour it exists to produce** rather
than by re-asserting its algebra. Re-stating `S(t) = S(t−1) + …` in a test
proves only that it was typed twice.

`tests/helpers.py::assert_feasible` independently re-derives §4.1 through §4.7
from any plan. It runs against synthetic shapes, the clock-change week, and
the full three-year output.

```bash
uv run pytest        # 118 tests, ~50 s. The MILP tests need no spreadsheet,
                     # the loader tests need no solver.
```

| File | Tests | Covers |
| --- | --: | --- |
| `test_window_problem.py` | 11 | Each constraint by the behaviour it produces: flat prices stay idle, a 5% spread is declined against the 0.9025 round trip, a dear Market 2 never tempts a simultaneous buy-and-sell, Market 2 holds flat across the hour while Market 1 moves within it, cycles accrue on discharge only, degradation blocks a refill to nominal |
| `test_rolling_horizon.py` | 10 | The handover, the discarded lookahead, one window reproducing the undecomposed solve exactly, and both [cycle-budget](cycle-budget.md) cases, ample and binding |
| `test_periods.py` | 5 | Hourly prices repeated across their pair, the [mislabelled spring hour](data.md#the-quirks-surfaced-and-deliberately-not-repaired) relabelled without reordering prices, whole-hour slicing, mismatched resolutions rejected |
| `test_plan.py` | 6 | Revenue priced on energy *delivered* not drawn, solver noise reported as zero, §4.7 volumes, empty-plan summary |
| `test_data_io.py` | 4 | The spec against Attachment 1, both series at their native resolutions, the clock-change artefacts flagged |
| `test_constraints.py` | 13 | Each constraint block against the rows it adds, without a solver: the named rows per period, §4.5 tying only the second half of each hour, the opening state read only in period 0, `DEFAULT_BLOCKS` accounting for every row the assembled model holds, and §4.6's cap imposed as a row with `n_cyc` left free, so that it can be relaxed |
| `test_cycle_value.py` | 14 | The two cycle-budget searches of §6: that a relaxed pass really overspends the budget and a capped one reports no usable slope, that the oracle counts and reuses its passes, the master LP's envelope minimum against cuts whose answer is known on paper, both methods reaching the same plan, and the dual bound holding above an exactly solved optimum |
| `test_cli.py` | 4 | Both commands end to end, including the written plan's dates and length, and that the result stays on stdout under every progress mode |
| `test_historical_slices.py` | 32 | The model against frozen optima on real slices of Attachment 2: five single days and three whole weeks. For each, that the rolling policy of §6 reaches the slice's exact optimum, that `summarise` reconciles with it, that energy left in the store was never paid for, and — the slow half of the suite — that the frozen optimum still re-solves as the optimum, so the reference values cannot rot behind a change to the formulation |
| `test_reporting.py` | 19 | What a run says while it runs: that a search is silent unless asked, that each method fills its own columns and bisection quotes no bound, that the early exit and both recovery outcomes are announced, that a cache hit is reported as one, that a redirected stream gets no cursor control, and the pass projection from a contracting gap |

A strict `mypy` pass and `ruff` run alongside.

## Two settings the checks pin down

**The zero-cleaning threshold is 10 W.** A MILP is solved to a feasibility
tolerance, so a solver may return a charge variable at 1e-6 MW in a period where
the battery discharges — enough to fail a §4.3 check on one period out of
52,608, while being 1.36 µW of physically meaningless noise. The threshold sits
an order of magnitude above the solver's tolerance so that the saved plan
verifies as it stands, with no post-processing, and a test holds it there.
Cleaning at that level moves profit by nothing at the penny.

**The default output format is CSV.** Parquet is offered through `--out` but
needs an engine this project does not ship, so a run that printed its results
could still fail at the write. CSV needs nothing extra, and a CLI test covers
the written file end to end.

Neither would be visible in a run that completed and printed plausible
numbers.

## Still open

- The dual bound is validated to 90 days, not to three years. Weak duality needs
  each pass to be a true maximum of the relaxed problem, and a rolling pass with
  one day of lookahead is a heuristic. The bound held above the proven optimum in
  all eight horizons swept, 1 to 90 days; the full horizon is twelve times the
  longest of them and has no proven optimum to check against.
  ([the sweep](model/cycle-value-experiments.md#real-prices-horizon-by-horizon) ·
  [the limits](model/cycle-value-experiments.md#4-limits))
- Foresight is checked on one month, June 2018. A month where the cycle budget
  mattered would test it harder.
  ([the measurement](solve.md#is-one-day-of-foresight-enough))

---

Figures from `data/results/dispatch_plan.csv`. Profit reproduces to the penny
across independent full-horizon runs; the period counts can move by one or two
of 52,608, where a tie between an idle period and a near-zero trade is broken
differently. Formulation: [`model/model.md`](model/model.md) §1–§7.
