# Glossary

*Every term the model, the code and the write-up use, with the one word chosen
for each idea — and the words deliberately not used.*

[← README](../README.md) · [data](data.md) · [architecture](architecture.md) ·
[solve](solve.md) · [cycle budget](cycle-budget.md) ·
[bisection](bisection.md) · [validation](validation.md)

---

## 1. One idea, one word

Three words were each carrying two or three unrelated meanings. The rule from
here on is that each row below has exactly one name, and the collided readings
get their own.

| Idea | The word | Never called |
| --- | --- | --- |
| Energy flowing into the battery | **charge** (`charge_1_mw`) | — |
| Energy in the store | **storage**, `S(t)` | *charge*, *state of charge* |
| λ, the worth of one cycle of budget | **cycle value** | *charge*, *fee*, *the Lagrangian* |
| `L(λ)`, the relaxed problem's optimum | **Lagrangian** | *value* |
| £/MWh quoted by a market | **price** (`price_1`, `price_2`) | — |
| The half-hourly time axis | **settlement periods** | *grid* (that is the electricity network) |
| The model's output | **dispatch plan** | *schedule* |

Two consequences worth stating plainly. **`price` now only ever means a market
price**: λ is a value, not a price, even though it is formally a shadow price.
And **`grid` is retired from the codebase entirely** — in a battery-trading
document the word belongs to the network, and using it for a discretisation
invites exactly the wrong reading.

## 2. The renames this implies

### Modules

| Now | Becomes | Why |
| --- | --- | --- |
| `modelling/grid.py` | `modelling/periods.py` | Uses the market's own word for the time axis; frees *grid* for the network |
| `modelling/rolling.py` | `modelling/rolling_horizon.py` | Names the method, not just its adjective |
| `modelling/milp.py` | `modelling/window_problem.py` | Holds *the problem over one window*; MILP is equally true of `constraints.py`, and plain `window` is the time span |
| `modelling/dispatch.py` | `modelling/policy.py` | A rule mapping prices to actions is a policy |
| `modelling/schedule.py` | `modelling/plan.py` | One word for the deliverable |
| `modelling/pricing.py` | `modelling/dual_problem.py` | Holds the dual objects: the oracle, the points, the bound |
| `modelling/pricers.py` | `modelling/dual_search.py` | The methods search the dual for the cycle value |

The names now read the decomposition off a directory listing, smallest scope
first: `periods.py` the half-hourly axis, `window_problem.py` one MILP over one
window, `rolling_horizon.py` the sequence of them covering the horizon,
`dual_problem.py` the subproblem at one cycle value over that whole horizon, and
`dual_search.py` the methods that choose the next cycle value to try.

### The time axis

| Now | Becomes |
| --- | --- |
| `DispatchGrid` | `SettlementPeriods` |
| `build_grid` | `build_periods` |

A `SettlementPeriods` instance is bound as `settlement`, never `periods`: that
name is already a *count* of half hours (`PERIODS_PER_DAY`, `commit_periods`,
`ctx.periods` as an index range).

### The policies

| Now | Becomes | Why |
| --- | --- | --- |
| `Dispatcher` | `DispatchPolicy` | Fits the receding-horizon framing |
| `RollingDispatcher` | `RollingPolicy` | One of several policies, not *the* dispatcher |
| `CalibratedDispatcher` | `CalibratedPolicy` | A policy that calibrates the cycle value first |
| `RollingPolicy.run_on_grid` | `.dispatch` | `run_on_periods` is ugly; `run` takes raw inputs, `dispatch` a prepared axis |
| `CalibratedDispatcher.price_and_dispatch` | `.calibrate_and_dispatch` | *Price* is retired as a verb |

### The dual search

| Now | Becomes | Why |
| --- | --- | --- |
| `CyclePricer` | `DualSearch` | A search rule over the dual, plus its relaxation |
| `CyclePricer.price(oracle)` | `DualSearch.search(oracle)` | — |
| `BisectionPricer` · `CuttingPlanePricer` | `BisectionSearch` · `CuttingPlaneSearch` | Follows the protocol |
| `PricingResult` | `DualSearchResult` | — |
| `PRICERS` · `DEFAULT_PRICER` · `pricer_named` | `SEARCHES` · `DEFAULT_SEARCH` · `search_named` | — |
| `calibrate_cycle_price` | `calibrate_cycle_value` | — |
| `cycle_price` (field, parameter, local) | `cycle_value` | λ is the worth of a cycle |
| `CycleOracle.at(price=…)` | `.at(cycle_value=…)` | — |
| `DualPoint.price` · `PricingResult.price` | `.cycle_value` | — |
| `DualPoint.value` | `.lagrangian` | It is `L(λ)`; *value* was the overloaded word |
| `DualPoint.feasible` | `.within_budget` | *Feasible* already means solver-feasible |
| `DualBound.value` · `.master_value` | `.lagrangian` · `.envelope` | Names the two things that bracket `min L(λ)` |
| `SPENT_IN_FULL` | `SPENT_TOLERANCE` | It is a tolerance, not a predicate |

### The formulation

| Now | Becomes | Why |
| --- | --- | --- |
| `effective_volume` (constraint block) | `volume_limit` | Collided with the *quantity* `effective_volume` in `plan.py` |
| `RELAXED_BLOCKS` | `UNCAPPED_BLOCKS` | "Relaxed blocks" reads as *blocks that are relaxed*; what is meant is the model with the cap gone |
| `ctx.keep_charged` | `ctx.retained` | Pairs with the existing `delivered`: `1 - e_c` in, `1 - e_d` out |
| `DispatchVariables.charging` | `.is_charging` | A binary flag named like a quantity, beside `charge_1_mw` |
| `cycles_used` (local, `profit_objective`) | `cycles_this_window` | Collided with `cycles_used` in the summary, which is the horizon total |

### The output

| Now | Becomes | Why |
| --- | --- | --- |
| `build_schedule` | `build_plan` | — |
| `storage_max_mwh` (column) | `effective_volume_mwh` | Named like a constant; it is time-varying |
| `revenue_1_gbp` · `revenue_2_gbp` · `revenue_gbp` | `net_revenue_1_gbp` · `net_revenue_2_gbp` · `net_revenue_gbp` | The columns are net of purchases, which the name can carry instead of a docstring warning |
| `data/results/dispatch_schedule.csv` | `dispatch_plan.csv` | — |

### Command line, scripts and files

| Now | Becomes |
| --- | --- |
| `--cycle-price` · `--cycle-pricer` | `--cycle-value` · `--search` |
| `scripts/compare_pricers.py` · `scripts/sweep_pricers.py` | `compare_searches.py` · `sweep_searches.py` |
| `scripts/sweep_pricers.py --pricer` | `scripts/sweep_searches.py --search` |
| `scripts/solve_monolith.py` | `scripts/solve_exact.py` |
| `docs/model/cycle-price-experiments.md` | `cycle-value-experiments.md` |
| `docs/model/cycle-price-sweep.csv` · `cycle-price-long-horizons.csv` | `cycle-value-sweep.csv` · `cycle-value-long-horizons.csv` |
| `tests/test_grid.py` · `test_rolling.py` · `test_milp.py` · `test_schedule.py` · `test_pricing.py` | `test_periods.py` · `test_rolling_horizon.py` · `test_window_problem.py` · `test_plan.py` · `test_dual_problem.py` |

## 3. The data

**Market 1** — the half-hourly market. 48 prices per day, settled per
settlement period. Its timestamp labels are unreliable at spring clock changes;
see [data](data.md).

**Market 2** — the hourly market. 24 prices per day. Its labels are taken as
canonical and the time axis is relabelled from them. A trade here is committed
for the whole hour (§4.5).

**Settlement period** — half an hour, the finest resolution either market
settles at and the model's time step. `dt = 0.5` hours, `PERIOD_HOURS`.

**Settlement periods** (`SettlementPeriods`) — both markets projected onto one
half-hourly axis: `timestamps`, `price_1`, `price_2`, equal length. Market 2's
hourly price is repeated across the two half hours it covers; the pairing is
positional, not by timestamp.

**Horizon** — the whole span being dispatched over: 52,608 periods, 2018–2020.

**Window** — a contiguous slice of the horizon handed to the solver as one MILP.

**Battery spec** (`BatterySpec`) — Attachment 1 as loaded, in the
spreadsheet's own units. **Model parameters** (`ModelParameters`) — the same
numbers converted once into the model's units (§2).

## 4. The battery

**Storage** — energy in the store, `S(t)` MWh, `storage_mwh`. The battery
starts empty.

**Nominal volume** — `S_nom`, the spec's capacity. **Effective volume** —
`S_max(t)`, the usable capacity after degradation (§4.7), reported as
`effective_volume_mwh`; in the formulation it is substituted out rather than
carried as a variable, by the `volume_limit` block.

**Charge / discharge** — energy in / energy out, MW per market
(`charge_1_mw`, `discharge_2_mw`, …).

**Charging loss / discharging loss** — `e_c`, `e_d`. The share lost on each
side, so `1 - e_c` reaches the store and `1 - e_d` reaches the buyer.
**Round-trip efficiency** — `(1 - e_c)(1 - e_d)`, 0.9025 as specified.

**Equivalent full cycle (EFC)** — one full discharge of nominal volume, the
unit the cycle count and the degradation rate are quoted in. `n_cyc(t)`,
`cycles`, non-decreasing.

**Degradation** — the fraction of nominal volume lost per EFC.

**Cycle budget** — `B`, the cap on `n_cyc(T)` over the horizon (§4.6): 5,000
cycles, or the **pro-rated budget** (1,500) when the asset's calendar life is
charged for instead (§5).

**Battery state** (`BatteryState`) — the two quantities a window hands the
next: `storage_mwh` and `cycles`.

## 5. The formulation

**Constraint block** — one function adding one section's rows to the problem.
`DEFAULT_BLOCKS` is the whole of §4; `UNCAPPED_BLOCKS` is §4 with the cycle cap
removed, for the Lagrangian relaxation.

**Mode exclusivity** — §4.3: no charging and discharging in the same period,
enforced by the binary `u(t)`. The reason the horizon cannot be one LP.

**Hourly commitment** — §4.5: a Market 2 decision is held across both half
hours of its hour.

**Relaxation** — dropping a constraint from the model. Here: removing the
cycle cap and charging the objective per cycle instead.

**Subproblem** — the problem a search asks the oracle for at a given cycle
value: §4 with the cap in place (capped) or removed (uncapped). It is defined by
its *relaxation*, not by its time extent — one subproblem spans the whole
horizon, and is covered by a sequence of window problems.

**Window problem** — the MILP over one window: the objective of §3 and the
blocks of §4, assembled from that window's prices and the state handed over to
it. Distinct from the **window** itself, which is only the span of periods.

**Window solution** (`WindowSolution`) — the decisions read back from one
solved window problem, period by period.

## 6. The decomposition

**Rolling horizon** — covering the horizon with a sequence of windows, each
committing part of its decisions and discarding the rest (§6).

**Commit periods** — how much of a window is kept. **Lookahead periods** — how
far past the committed part the window sees before that part is discarded. Both
must be whole hours, so the hourly commitment is never split.

**Handover** — passing the `BatteryState` from one window to the next. Exact
for storage; the cycle budget is what the handover alone cannot get right.

**Dispatch policy** (`DispatchPolicy`) — anything mapping prices to a dispatch
plan. `RollingPolicy` is the formulation of `model/model.md`;
`CalibratedPolicy` calibrates the cycle value first, then dispatches at it.

**Dispatch plan** — the output: one row per settlement period holding the
decisions, the storage and cycle trajectories, and the revenue. Every figure
quoted anywhere is recomputed from these columns.

**Pass** — one run of a policy over the whole horizon, ≈77 s on this data. The
unit the search's cost is counted in.

## 7. The dual search

**Cycle value** — λ, in £ per EFC: what one cycle of budget is worth. It enters
each window's objective, so a window spends a cycle only on a spread that beats
it. The value that makes the horizon spend exactly its budget is the budget's
shadow price.

**Shadow price** — the formal name for λ: the rate at which the optimum
improves per unit of budget relaxed.

**Lagrangian** — `L(λ)`, the relaxed problem's optimum at a given cycle value.
An upper bound on the constrained optimum for every λ, by weak duality.

**Subgradient** — `B - n_cyc(T)`, the slope of `L` at λ. Exact only if the pass
maximised the relaxed problem, which a finite lookahead approximates. Zero
wherever a cap binds, which is why a method that reads slopes needs relaxed
passes.

**Capped pass / relaxed pass** — a pass with the cycle cap in place (its plan
is deliverable, its subgradient uninformative) or without it (its subgradient
is usable, its plan is not deliverable).

**Oracle** (`CycleOracle`) — one capped-or-relaxed pass at one cycle value,
memoised and counted. The one place the expensive primitive lives, so pass
counts are measured rather than asserted.

**Dual point** (`DualPoint`) — everything one pass yields: the cycle value, the
Lagrangian, the subgradient, the profit, the cycles, and the plan.

**Cut** — the inequality `L(λ) ≥ lagrangian + subgradient · (λ - cycle_value)`
a dual point contributes. **Envelope** — the minimum of the cuts, a lower bound
on `min_λ L(λ)`.

**Dual bound** (`DualBound`) — the best Lagrangian evaluated (upper) and the
envelope minimum (lower), with the **gap** between them that the search
terminates on.

**Dual search** (`DualSearch`) — a method for finding the cycle value: a search
rule *and* a choice of relaxation. Two are implemented.

**Bisection search** — bisects λ on capped passes, reading one bit per pass
("was the budget exhausted?"). Certifies nothing.
See [bisection](bisection.md).

**Cutting-plane search** — Kelley's method on relaxed passes: each pass adds a
cut, the next λ minimises the envelope, and the gap certifies the answer. The
default. See [cycle budget](cycle-budget.md).

**Calibration** — running a dual search to fix the cycle value before
dispatching at it.

## 8. The output

**Profit** — the objective of §3 summed over the horizon: energy sold at each
market's price less energy bought. Capex and fixed opex are excluded; per §5
they do not depend on the dispatch decision.

**Net revenue** — income less the cost of what was bought, per market
(`net_revenue_1_gbp`, `net_revenue_2_gbp`) and across both (`net_revenue_gbp`).
Being net is why a market the battery mostly buys in carries a negative total
while profit across both is positive.

**Income / cost** — the gross halves of profit, reported separately so the mean
buy and sell prices can be read off.

**Summary** (`summarise`) — the headline figures for a plan (§7), recomputed
from its columns so the write-up and the code cannot drift.
