# Build report: the cycle-pricer seam

*What was built for the two pricing methods of §6, what was deviated from the
proposal, and the evidence it was checked against. Written 2026-10-17, against
the block refactor in [`3dd8cce`](#how-to-reproduce).*

[← README](../README.md) · [architecture](architecture.md) ·
[cycle budget](cycle-budget.md) · [pricing experiments](model/cycle-price-experiments.md) ·
[validation](validation.md)

---

The design is in
[architecture §4](architecture.md#4-two-ways-to-price-the-cycle-budget) and the
measurements in
[cycle-price-experiments](model/cycle-price-experiments.md). This page is the
record of the build itself: the file-by-file inventory, the three places the
implementation departed from the proposal, and the verification evidence — the
things a reviewer would otherwise have to reconstruct from the diff.

## What was built

| File | Status | What it holds |
| --- | --- | --- |
| `modelling/pricing.py` | new, 184 lines | The seam: `DualPoint`, `DualBound`, `PricingResult`, `CycleOracle`, the `CyclePricer` protocol. No algorithm. |
| `modelling/bisection.py` | new, 77 lines | `BisectionPricer` — the existing search, moved behind the seam, on capped passes, `bound=None`. |
| `modelling/cutting_plane.py` | new, 112 lines | `CuttingPlanePricer` and `solve_master` — relaxed passes, cuts, the two-variable master LP, the recovery pass. |
| `modelling/pricers.py` | new, 98 lines | `PRICERS`, `CalibratedDispatcher`, `pricer_named`, and `calibrate_cycle_price` as the compatibility wrapper. |
| `modelling/constraints.py` | changed | `n_cyc` declared without an upper bound; `relaxing(*blocks)` and `RELAXED_BLOCKS`; `mode_exclusivity` docstring states what omitting it removes. |
| `modelling/rolling.py` | changed | A `blocks` field on `RollingDispatcher`, passed to `solve_window`; `calibrate_cycle_price` moved out. |
| `modelling/__init__.py` | changed | Exports the pricing types; `calibrate_cycle_price` now re-exported from `pricers`. |
| `cli.py` | changed | `--cycle-pricer {bisection,cutting-plane}`, and a report of the charge, the passes and the bound. |
| `scripts/compare_pricers.py` | new, 74 lines | Every method in `PRICERS` over one instance, with a single-MILP ground truth up to 30 days. |
| `scripts/sweep_pricers.py` | new, 200 lines | The same over a progression of horizons, writing `docs/model/cycle-price-sweep.csv`; `--pricer`, `--no-exact` and `--out` take it past the horizons a one-shot MILP can check, into `cycle-price-long-horizons.csv`. |
| `tests/test_pricing.py` | new, 14 tests | The seam and both methods — see [validation](validation.md). |
| `tests/test_constraints.py` | changed | The cycle bound test replaced by one pinning that `n_cyc` is free so the cap can be relaxed. |

The layering, which is what the review should check holds:

```
bisection.py · cutting_plane.py     the two search rules
  ──────── CyclePricer ────────     the seam; PRICERS is the catalogue
pricing.py · CycleOracle.at(λ, relaxed=…) → DualPoint
rolling.py · RollingDispatcher(blocks=…)  one pass over the horizon
constraints.py · DEFAULT_BLOCKS / RELAXED_BLOCKS
```

Neither pricer builds a model, and neither `rolling.py` nor anything below it
imports a pricer.

## Three deviations from the proposal

**Four modules, not three.** `pricing.py` holds `CycleOracle`, which needs
`RollingDispatcher`, so a registry inside `pricing.py` importing both algorithms
would have closed an import cycle. `PRICERS` and `CalibratedDispatcher` went
into a small fourth module, `pricers.py`.

**`calibrate_cycle_price` moved to `pricers.py`.** The proposal kept it in
`rolling.py` as a wrapper, but that file is imported *by* `pricing.py`, so a
wrapper there would have had to import `bisection.py` and cycle. mypy's strict
`no_implicit_reexport` rules out re-exporting it from `rolling.py` without
ceremony, so the two call sites in `tests/test_rolling.py` and the line in
`modelling/__init__.py` were updated instead. The public name
`battery_case.modelling.calibrate_cycle_price` is unchanged, and so is its
signature and return type.

**The experiments doc lives under `docs/model/`.** The README already pointed at
`docs/model/cycle-price-experiments.md`, and the dead link in `model.md` §6 was
relative to its own directory, so that was always the intended path.

## The proposal item that was not built

Phase 1 called for splitting the aggregate rate caps out of `mode_exclusivity`,
because omitting that block lifts peak `c1 + c2` to 4 MW against the 2 MW spec.
**Not done**, for two reasons:

- **Cost.** Always-on rate rows are two rows per period: 315,649 rows on the
  horizon become 420,865, a third more, to make safe a relaxation that nothing
  runs. The cycle cap is the only constraint either method prices.
- **The write-up.** §4.3 states the rate limit and the binary coupling as one
  pair of inequalities, so a block that is one *section* is also one *concept*.
  Removing §4.3 means removing that inequality.

What was done instead: the block's docstring states that omitting it removes the
rate caps with the binary, and the measurement is kept in
[cycle-price-experiments](model/cycle-price-experiments.md) as the reason it is
documented rather than split. If the rows are judged worth paying, it is a
ten-line change — a `rate_limits` block in `DEFAULT_BLOCKS` and two row names.

## Verification evidence

### The default model is unchanged

| Check | Before | After |
| --- | --- | --- |
| Rows / columns, 48-period grid | 289 / 336 | 289 / 336, row names identical |
| Rows / columns, full horizon | 315,649 / 368,256 | 315,649 / 368,256 |
| `scripts/solve_monolith.py 7 120` | £1,231.12, Optimal | £1,231.12, Optimal |
| 60-day rolling dispatch | £12,956.528606, 175.658857 cycles | £12,956.528606, 175.658857 cycles |

The last row is the one that matters for freeing the `n_cyc` bound: it was
measured by restoring the old bound, re-running, and diffing — identical to six
decimals, as a change that does not move the feasible set should be.

### The relaxation now relaxes

Three-day instance, budget 1.0 cycle, one MILP per figure:

| | capped | relaxed |
| --- | --: | --: |
| cycles at λ = 0 | 1.000 | 3.000 |
| subgradient at λ = 0 | 0.000 | −2.000 |
| subgradient at λ = 100 | 0.000 | −2.000 |
| subgradient at λ = 300 | 0.000 | 0.000 |

Before the `n_cyc` bound was freed, the relaxed column was the capped one:
omitting `cycle_life_cap` changed nothing, because the budget was also the
variable's upper bound.

### Both methods, against an exact answer

Eight horizons, each priced against half of what it spends unpriced, each with
the capped program also solved whole
([`cycle-price-sweep.csv`](model/cycle-price-sweep.csv), from
`scripts/sweep_pricers.py`):

| Days | Exact | bis passes | bis λ | bis profit | cut passes | cut λ | cut profit | cut bound | cut − bis |
| --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| 1 | £131.45 | 13 | £11.28 | £131.45 | 7 | £11.33 | £130.10 | £131.45 | −1.03% |
| 2 | £310.41 | 13 | £18.80 | £310.41 | 9 | £18.82 | £309.23 | £310.41 | −0.38% |
| 4 | £576.26 | 13 | £21.48 | £575.55 | 9 | £21.52 | £575.55 | £576.26 | 0.00% |
| 7 | £1,133.62 | 13 | £22.51 | £1,133.62 | 7 | £22.66 | £1,131.23 | £1,133.63 | −0.21% |
| 14 | £2,190.84 | 13 | £24.71 | £2,176.81 | 8 | £24.49 | £2,176.81 | £2,190.88 | 0.00% |
| 30 | £4,937.98 | 13 | £28.47 | £4,937.33 | 7 | £28.85 | £4,935.43 | £4,938.22 | −0.04% |
| 60 | £11,948.15 | 13 | £30.81 | £11,945.75 | 9 | £29.86 | £11,936.95 | £11,948.60 | −0.07% |
| 90 | £17,594.04 | 13 | £36.77 | £17,592.95 | 9 | £36.17 | £17,577.53 | £17,594.31 | −0.09% |

Plus the three-day test instance, where cutting planes closes to a **zero** gap
in 3 passes and so proves its £1,435.79 optimal for the relaxation.

Three claims the sweep settles:

- **The bound holds in all eight rows**, above the proven optimum every time — by
  1p at seven days, 27p at ninety. `test_the_dual_bound_is_not_below_the_exact_optimum`
  keeps the three-day case honest in CI; the sweep is what extends the check to 90
  days, which the first draft of these docs listed as open.
- **Cutting planes reproduces the bisection**, and better as the horizon grows:
  −1.03% at one day, under a tenth of a percent from four days on, identical to
  the penny at 4 and 14 days. The charges agree throughout (£36.77 against
  £36.17 at ninety days).
- **It is cheaper in every row**: 7–9 passes against a fixed 13, mean 8.4, and
  lower wall clock throughout — 35.6 s against 44.7 s at ninety days.

One incidental finding worth recording: every row here proved optimal as one
MILP, **including 60 days**, which [`tractability.md`](model/tractability.md)
could not prove in 900 s. Not a contradiction — a cycle budget halved against
unpriced use is itself a strong constraint, and it prunes the search the
unconstrained window leaves open.

### Suite, types, lint

```
64 passed in 10.00s          # 49 from before + 1 in test_constraints + 14 in test_pricing
mypy: Success, 31 source files, strict
ruff check . && ruff format --check .   # clean
```

A correction to carry forward: the suite was documented as "~22 s" after the
block refactor, which was a cold-cache run. It measures ~10 s consistently, and
the docs now say that.

### Both methods through the CLI

```
$ uv run battery-case dispatch --start 2018-06-01 --end 2018-06-03 --cycle-pricer bisection
  cycle charge                               0.00 GBP/cycle
  horizon passes spent                          1
  dual bound                        not available

$ uv run battery-case dispatch --start 2018-06-01 --end 2018-06-03 --cycle-pricer cutting-plane
  cycle charge                               0.00 GBP/cycle
  horizon passes spent                          1
  dual bound on profit                     427.07 GBP
  dual gap                                0.000%
```

The ample budget is the headline case and neither method fires on it: `λ* = 0`
after one pass, which is also what `tests/test_pricing.py` asserts.

## What is still open

- **The three-year priced run.** Now run with cutting planes: 10 passes,
  12 min 49 s, λ = £30.17, a schedule within 1.73% of the bound. The ~10 minutes
  a pass quoted here was wrong by an order of magnitude; a pass is ~77 seconds.
  What remains open is a check — the ground-truth MILP which validated the bound
  at 30 days cannot be built at this size, which is the point of having a
  bound.
- **The bound at 60 and 90 days.** Weak duality needs each pass to be a true
  maximum of the relaxed problem, and a rolling pass with one day of lookahead
  is a heuristic. It held at 7 and 30 days; that should be repeated before a
  bound is quoted on three years.
- **The vector case.** A per-year quota needs one multiplier per period and a
  stabilised master. The master LP absorbs it by adding columns; nothing in the
  seam assumes a scalar except the two methods themselves.

## How to reproduce

```bash
git log --oneline -1                           # 3dd8cce — the commit this was built on
uv run pytest                                  # 64 tests
uv run python scripts/compare_pricers.py 30    # one instance, with ground truth
uv run python scripts/sweep_pricers.py         # 1,2,4,7,14,30,60,90 days — the table above
uv run python scripts/solve_monolith.py 7 120  # £1,231.12 — the unchanged default model
```

`compare_pricers.py` takes the budget as a second argument and otherwise prices
against half of what the horizon spends unpriced, which is the instance where
the cap binds hard enough for the methods to differ.
