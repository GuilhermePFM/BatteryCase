# Solver parameter tuning

*What a full rolling pass spends its time on, why the window MILPs never
branch, and which HiGHS settings move the number.*

[← README](../../README.md) · [model](model.md) · [solve](../solve.md) ·
[tractability](tractability.md) · [cycle budget](../cycle-budget.md) ·
[validation](../validation.md)

---

[`tractability.md`](tractability.md) measures the choice between one MILP and a
sequence of them. This file measures the sequence itself: one pass of
`RollingPolicy` over the three-year horizon — 1,096 window MILPs of 96 periods,
48 committed and 48 of lookahead — and asks what the 435 seconds are made of.

Every number below keeps the binaries of §4.3 in the model. Nothing here
relaxes the mode exclusivity or drops a constraint block; the comparisons are
between ways of *solving* the same formulation, except in §5 and §6 where a
window geometry or a process split is varied, which is marked as such.

Measured on this machine: HiGHS 1.15.1 in process via pulp 4.0.1, 20 cores,
one `HiGHS` object reused across every window as the loop already does. **All
timings on this page were taken on an otherwise idle machine.** An earlier
round was measured against a competing CPU process and has been discarded; the
grid of §3 reproduced on the idle machine to within 1.5 ms per cell with the
ordering unchanged, so the contention was uniform, but the absolute times were
inflated by 3–4% and are not the ones quoted here.

## The settings that came out fastest

Now the default in `default_solver`, as
`battery_case.modelling.window_problem.TUNED_OPTIONS`:

```python
pulp.HiGHS(
    msg=False,
    mip_allow_restart=False,
    mip_heuristic_run_rins=False,
    mip_heuristic_run_feasibility_jump=False,
)
```

Full three-year horizon, against the £207,365.00 that
[`tractability.md`](tractability.md#what-the-comparison-says) brackets:

| | Seconds | Speed-up | Profit | Cycles |
| --- | --- | --- | --- | --- |
| 48/48, stock HiGHS | 434.6 | 1.00× | £207,365.04 | 3,443.0 |
| **48/48, tuned (shipped)** | **176.0** | **2.47×** | £207,365.09 | 3,442.6 |
| 48/24, stock HiGHS | 184.1 | 2.36× | £207,365.27 | 3,442.7 |
| **48/24, tuned (shipped)** | **78.4** | **5.54×** | £207,365.34 | 3,442.4 |

The settings are free: profit moves by £0.05 on a £207,365 plan, **upwards**,
which is solver noise rather than a gain. Every configuration measured on the
full horizon lands within £0.40 of every other, and the reference slices of
`tests/test_historical_slices.py` still reproduce their known optima to
**6e-11** relative.

The 2.47× on a real pass exceeds the 1.82× the per-window benchmark of §3
predicts, because the per-window figure carries ~6 ms of pulp build and
transfer (§1) that no solver option can touch.

**This is not the fastest configuration measured.** Adding
`mip_heuristic_run_root_reduced_cost=False` reaches 1.96× per window (8% faster
than the shipped 1.82×) and 142.1 s on the full horizon (19% less wall time than
176.0 s). It was **not** taken: it is the one setting measured here that costs
optimality rather than time, and §3 has the evidence.

## 1. The breakdown of one window

Instrumenting pulp's four solve stages over 40 windows, stock HiGHS:

| Stage | Per window |
| --- | --- |
| `build_problem` (pulp model assembly) | 4.35 ms |
| `buildSolverModel` (pulp → HiGHS transfer) | 1.78 ms |
| `callSolver` (HiGHS) | **123.75 ms** |
| `findSolutionValues` (reading values back) | 0.74 ms |

98% of a pass is branch-and-bound. Python is not the cost.

## 2. The windows never branch, and why

From `getInfo()` over 30 windows:

| | |
| --- | --- |
| MIP nodes | mean 1, median 1, max 1 |
| Simplex iterations | mean 746, max 1,930 |

One node. The windows are solved at the root, not in a tree. Parsing the
`BestBound` column out of the HiGHS log for 25 windows shows what closes the
gap there:

| | Above the MILP optimum |
| --- | --- |
| Pure LP relaxation (`mip=False`, no cuts) | 3.455% |
| HiGHS root bound, **first** table line | 3.455% |
| HiGHS root bound, **last** line still at node 0 | **0.018%** |

**Fraction of the integrality gap closed at the root, before any branching:
mean 99.46%, median 99.99%, worst window 96.66%.**

The root LP starts 3.46% high; the finished root is 0.018% high, which is at
the default termination tolerance once a matching incumbent exists. Nothing is
left to branch on. These are counts and bounds rather than timings, so they are
unaffected by machine load.

The structural reading: strip the two markets and each period carries a flow
balance (`storage[t] = storage[t-1] + inflow − outflow`), a capacity bound on
the flow, and a binary switching that flow on or off at a **tight** big-M — `M`
is exactly `max_charge_mw`, not a loose bound. That is a capacitated
fixed-charge flow, the same skeleton as single-item capacitated lot-sizing,
where the mixed-integer-rounding and flow-cover cut families come close to
describing the convex hull. Chained over 96 periods it stays in that family.
*This paragraph is the reading, not a measurement:* the 99.46% is measured, and
the log reports 225 cuts generated with 45 in the LP, but HiGHS does not break
cuts down by family and offers no option to disable one, so which separator
fires was not verified.

The log for a single window, for the shape of it:

```
 R       0       0         0   0.00%   380.9532714     362.4310547        5.11%        0      0      0       275     0.0s
 L       0       0         0   0.00%   365.3716861     365.1476087        0.06%      225     45      0       322     0.1s

26.0% inactive integer columns, restarting
Model after restart has 353 rows, 407 cols (70 bin., 0 int., 0 impl., 337 cont., 0 dom.fix.)

Solving report
  Status            Optimal
  Gap               0.000283% (tolerance: 0.01%)
  Timing            0.22
                    0.21 (Solve)
                        MIP    time [calls] = 0.06 [1]
                        subMIP time [calls] = 0.15 [7]
  Nodes             1
  LP iterations     1296
                    23 (strong br.)
                    51 (separation)
                    911 (heuristics)
```

The root reaches a 0.06% gap at 0.1 s and 322 iterations. The rest of the solve
is seven sub-MIP heuristic calls and one restart. 911 of the 1,296 LP
iterations are heuristics.

## 3. The heuristics, swept exhaustively

The four MIP heuristics HiGHS enables by default are RINS, RENS,
`root_reduced_cost` and `feasibility_jump`. They **do not compose**, so they
cannot be ranked one at a time: the full 2⁴ was measured, with `restart` off
throughout, plus stock HiGHS as the reference. 100 consecutive windows, 3
interleaved repetitions, median reported. Run-to-run spread was 0.01–0.67 ms
against effects of up to 65 ms.

| Config (restart off unless stated) | ms/window | Speed-up | vs stock | Worst window |
| --- | --- | --- | --- | --- |
| **no RINS + no rootRC + no feasJump** | **67.00** | **1.96×** | −0.0000% | −0.001% |
| no RENS + no rootRC + no feasJump | 69.09 | 1.91× | −0.0000% | −0.001% |
| no RINS + no rootRC | 71.97 | 1.83× | −0.0000% | −0.001% |
| no RINS + no feasJump | 72.46 | 1.82× | −0.0000% | −0.001% |
| no RENS + no rootRC | 74.19 | 1.77× | −0.0000% | −0.001% |
| no RINS | 77.74 | 1.69× | −0.0000% | −0.001% |
| no RENS + no feasJump | 78.44 | 1.68× | −0.0000% | −0.001% |
| no RINS + no RENS + no feasJump | 82.87 | 1.59× | −0.0002% | −0.008% |
| no RENS | 84.37 | 1.56× | −0.0000% | −0.001% |
| no RINS + no RENS | 86.67 | 1.52× | −0.0002% | −0.008% |
| no rootRC + no feasJump | 94.51 | 1.39× | −0.0000% | −0.001% |
| no feasJump | 99.77 | 1.32× | −0.0000% | −0.001% |
| **all four off** | 101.08 | 1.30× | −0.0005% | −0.008% |
| no RINS + no RENS + no rootRC | 103.69 | 1.27× | −0.0005% | −0.008% |
| no rootRC | 104.14 | 1.26× | −0.0000% | −0.001% |
| heuristics all on, restart off | 109.27 | 1.20× | −0.0000% | −0.001% |
| stock HiGHS (all on, restart on) | 131.64 | 1.00× | — | — |

The shape of the result: **keep exactly one sub-MIP heuristic and turn off
everything else.** Turning off all four is 1.30×, barely better than turning
off none — the solver still needs one heuristic to produce the incumbent that
lets it terminate, and without any it pays for that elsewhere. With one kept,
RENS is the better survivor (1.96× against 1.91×).

Every config that keeps RENS also holds its worst single window to −0.001%,
while the configs that drop RENS sit at −0.008%. RENS occasionally finds a
genuinely better incumbent; the other three look like pure overhead on this
model.

`mip_heuristic_effort` is the wrong knob. It scales effort *inside* the
heuristics without stopping them firing, and `mip_heuristic_effort = 0` left
all seven sub-MIP calls in place with no measurable change.

### Why the fastest cell is not the shipped one

The top two cells both drop `root_reduced_cost`, and dropping it is the only
setting measured on this page that costs *optimality* rather than time. Run
against the reference slices of `tests/test_historical_slices.py`, which assert
the rolling dispatch reaches a known per-slice optimum to `rel=1e-5`:

| Config (restart off) | ms/window | Worst relative error | Slices over 1e-5 |
| --- | --- | --- | --- |
| stock HiGHS | 537.8 | 5.47e-11 | 0 |
| no RINS | 173.3 | 5.64e-11 | 0 |
| **no RINS + no feasJump** | **166.5** | **5.64e-11** | **0** |
| no RINS + no rootRC | 142.0 | **1.67e-05** | 1 — 2019-05-11+7d |
| no RINS + no rootRC + no feasJump | 136.2 | **1.67e-05** | 1 — 2019-05-11+7d |

(ms/window here is over the test slices, which are shorter than the 96-period
windows of the main grid, so these times are not comparable with §3's.)

`root_reduced_cost` is the single cause: keep it and the slices come back exact
to eleven decimal places, drop it and the 2019-05-11 week lands £0.015 below its
known £903.457632 — 1.67e-5, outside the 1e-5 the tests allow. Note that §3's
aggregate column reads −0.0000% for that cell: averaged over 100 windows the
loss is invisible, and only the worst-window column (−0.001%) and the slice
tests expose it.

So the shipped configuration is the fastest cell that keeps every reference
value exact, at 1.82× instead of 1.96× per window — 176.0 s against 142.1 s on
the full horizon, 19% more wall time.

**That 19% was declined, and the decision is settled.** Taking it would mean
widening `_OPTIMALITY_RTOL` from 1e-5, which trades a documented correctness
check for speed; the reference slices reproducing their known optima exactly is
worth more than the time. This paragraph is here so the option is not re-opened
by someone reading the grid of §3 and noticing the faster cell: the faster cell
is known, measured, and rejected on purpose.

### An earlier, narrower grid

For the record, because it is how the above was arrived at and it shows the
hazard. A 2³ over {RENS, RINS, restart} alone, same protocol:

| Config | ms/window | Speed-up |
| --- | --- | --- |
| no RINS + no restart | 77.40 | 1.70× |
| no RENS + no restart | 83.61 | 1.57× |
| no RENS | 84.56 | 1.55× |
| no RENS + no RINS + no restart | 85.92 | 1.53× |
| no RENS + no RINS | 90.66 | 1.45× |
| no RINS | 96.83 | 1.36× |
| no restart | 108.74 | 1.21× |
| stock | 131.45 | 1.00× |

Three successive conclusions were drawn and overturned here: that RENS was the
knob to turn off (it is the one to keep), that `no RENS + no restart` was the
best pair (`no RINS + no restart` is 8% faster), and that
`root_reduced_cost` removal was harmful — it measured 1.20× on a
RENS-and-RINS-off base, and is worth 1.26× on its own and part of the winning
cell. Each reversal came from widening the grid. The knobs interact
non-monotonically, so partial grids around a single-knob leader are not safe
here.

### Settings that backfire

100 windows, single run, on top of `no RINS + no restart`:

| | Speed-up | Objective | Worst window |
| --- | --- | --- | --- |
| `mip_lifting_for_probing = 0` | **0.77×** | −0.0005% | −0.010% |
| `mip_root_presolve_only = true` | 1.61× (vs 1.69×) | −0.0000% | −0.001% |
| `presolve = off` | 1.65× (vs 1.69×) | −0.0000% | −0.001% |

Probing lifting is load-bearing for the bound, consistent with cuts doing all
the work: switching it off makes the solve 2.2× slower than leaving it alone.

### Settings that do nothing

Within ±3%, on top of `no RINS + no restart`: `mip_detect_symmetry` (1.74×),
`mip_lp_age_limit = 100` (1.72×), `mip_pool_age_limit = 100` (1.71×),
`mip_max_start_nodes = 0` (1.74×), `simplex_strategy = 1` (1.74×), against the
base's own 1.69×. Also neutral: `mip_heuristic_effort`, `mip_max_cutpool_age`,
`mip_pool_soft_limit`.

### The gap tolerances

100 windows, single run, on top of `no RINS + no restart` (1.69×):

| | ms/window | Speed-up | Total objective | Worst single window |
| --- | --- | --- | --- | --- |
| `gapAbs = 0.5` | 74.89 | 1.84× | −0.0007% | −0.036% |
| `gapAbs = 1.0` | 75.01 | 1.84× | −0.0027% | −0.161% |
| `gapRel = 1e-3` | 75.72 | 1.82× | −0.0070% | −0.100% |
| `gapRel = 1e-2` | 63.23 | 2.18× | −0.1855% | −0.982% |

An absolute gap behaves better than a relative one at this scale: a window's
objective is only £200–400, so one `gapRel` means a different amount of
absolute slack in every window of the horizon. None of these is used — the
heuristic settings of §3 reach 1.96× at −0.0000%, so a tolerance adds little
speed for the first real cost in objective.

## 4. Approaches that did not pay

### Warm starts

[`solve.md`](../solve.md) calls warm starting "the clearest remaining
speed-up, and it is not implemented". Consecutive windows overlap by 48
periods, so window *i* was seeded with window *i−1*'s solution shifted by 48 —
every variable of §2 including the binary — and solved with pulp's
`warmStart=True`, which hands the point to HiGHS as `setSolution`:

| | Per window | Committed profit, 80 windows |
| --- | --- | --- |
| `warmStart=False` | 140.31 ms | £17,387.59 |
| `warmStart=True` | 143.62 ms | £17,387.59 |

No gain, and marginally slower than not bothering. §2 is why: with a node count
of 1 there is no tree to prune, and an incumbent handed in at the start does not
spare the root its separation rounds.

### Solving the LP first

If the LP relaxation were usually integral, a window could be settled by one LP
and the MILP called only when it is not. Over 120 windows:

| | |
| --- | --- |
| LP solve | 5.25 ms |
| MILP solve | 144.60 ms (27.5×) |
| Windows whose LP relaxation is integral | **0 of 120** |
| LP objective above MILP objective | mean 3.65%, max 8.99% |

Never integral, never close. A fractional `u(t) = ½` admits half-rate charging
*and* half-rate discharging in the same period — cross-market simultaneous
arbitrage, buying in Market 1 and selling in Market 2 at the same instant. That
point is the midpoint of two integer-feasible points, so the single-period set
is already its own convex hull and no valid inequality in `(c, d, u)` cuts it
off. The binaries of §4.3 are what closes the 3.65%; they are necessary, but
§2 shows they are not *hard*.

### Fewer rows for Market 2's hourly commitment

§4.5 is currently 96 half-hourly variables for `c2`/`d2` plus 96 equality rows
tying each period to the one before. The same model can be written with 48
hourly variables and no equality rows. Built both ways over 80 windows:

| | Rows | Columns | Per window | Objective |
| --- | --- | --- | --- | --- |
| as shipped | 577 | 672 | 121.5 ms | £34,451.05 |
| hourly Market 2 variables | 481 | 576 | 120.5 ms | £34,451.05 |

Identical objective to the penny, confirming the two formulations are the same
model. No speed-up: presolve already performs the substitution, so those 96
rows and 96 columns were never solved over. (The two timings here are from the
contended round and were not re-measured; the identical objective and the
presolve explanation do not depend on them, but the 1 ms difference should not
be read as a measurement.)

## 5. Window geometry

Solve time grows superlinearly in the window length
([`tractability.md`](tractability.md#how-solve-time-grows-with-the-window)), so
shortening the lookahead pays more than proportionally. First 150 days, stock
HiGHS:

| commit / lookahead (periods) | Windows | Seconds | ms/window | Profit | vs 48/48 |
| --- | --- | --- | --- | --- | --- |
| 48 / 48 (as shipped) | 150 | 30.62 | 204.1 | £29,346.81 | baseline |
| 48 / 36 | 150 | 19.48 | 129.9 | £29,346.84 | +0.000% |
| **48 / 24** | 150 | **11.60** | 77.3 | £29,346.82 | **+0.000%** |
| 48 / 12 | 150 | 9.32 | 62.1 | £29,344.37 | −0.008% |
| 48 / 72 | 150 | 38.84 | 259.0 | £29,346.84 | +0.000% |
| 24 / 24 | 300 | 13.41 | 44.7 | £29,346.84 | +0.000% |
| 24 / 48 | 300 | 28.31 | 94.4 | £29,346.84 | +0.000% |
| 96 / 24 | 75 | 21.01 | 280.1 | £29,346.84 | +0.000% |
| 96 / 48 | 75 | 27.93 | 372.4 | £29,346.84 | +0.000% |
| 144 / 48 | 50 | 40.10 | 801.9 | £29,346.84 | +0.000% |

Twelve hours of foresight buys everything a full day of it does. Profit is flat
to the penny across almost the whole grid, which is
[`solve.md`](../solve.md#is-one-day-of-foresight-enough)'s observation from the
other side — committing a whole week at a time earns exactly the same as
committing a day. A 4 MWh store carries at most two hours of discharge across a
boundary, so no decision in a window reaches 24 periods past it.

Holding the lookahead fixed, the commit length buys nothing: `24/48`, `48/48`,
`96/48` and `144/48` all return the same profit while the per-window cost rises
from 94 ms to 802 ms.

Note that `--lookahead-days` is `type=int`, so a 24-period lookahead is not
reachable from the CLI as it stands.

## 6. Chunking the horizon across processes

The pass is sequential because each window hands `BatteryState` to the next, but
that handover is two floats. Splitting the horizon into *K* chunks solved in
parallel processes, each starting from an empty battery, leaves only *K−1* of
the 1,096 boundaries wrong — and storage at a day boundary is small anyway: over
the saved plan it averages **1.12 MWh** of a 4 MWh store, and exceeds 0.01 MWh
at 687 of 1,096 boundaries. Cycle counts are additive across chunks, so the
global total still reconciles while the budget does not bind.

First 150 days, `spawn` processes, serial reference in the same run, stock
HiGHS:

| | Seconds | Speed-up | Profit | vs serial |
| --- | --- | --- | --- | --- |
| serial | 35.06 | 1.00× | £29,346.81 | baseline |
| K = 5 | 11.44 | 3.06× | £29,370.31 | +0.080% |
| K = 10 | 10.12 | 3.47× | £29,335.90 | −0.037% |
| K = 15 | 7.66 | 4.57× | £29,345.99 | −0.003% |

The drift is not monotonic in *K* and changes sign — K = 5 came out £23 *ahead*
of the serial pass — so it is boundary noise rather than a cost of chunking. The
speed-up falls short of *K* because each spawned worker re-imports and re-reads
both spreadsheets, and because chunks differ in difficulty, so the pass ends
with the slowest one.

**`fork` does not work.** `ProcessPoolExecutor` defaults to it on Linux, and
forking after a `Highs` object has been constructed in the parent leaves the
workers spinning at 100% CPU indefinitely — five workers burned 22 minutes of
CPU each with no progress and had to be killed. `mp.get_context("spawn")`
avoids it; every parallel number above is from spawn.

## 7. The three stacked

First 150 days, each row adding to the one above, one process tree:

| | Seconds | Speed-up | Profit | vs A |
| --- | --- | --- | --- | --- |
| **A** 48/48, stock HiGHS | 31.86 | 1.00× | £29,346.81 | baseline |
| **B** A + lookahead 24 | 11.36 | 2.81× | £29,346.82 | +0.0001% |
| **C** B + no RINS + no restart | 7.69 | 4.14× | £29,346.82 | +0.0000% |
| **D** C + 15-way chunk parallel | 4.06 | **7.86×** | £29,345.99 | −0.0028% |

Rows C and D use `no RINS + no restart`, a two-knob configuration found before
the grid of §3 was widened; the shipped three-knob default is slightly faster
again (176.0 s against 182.6 s at 48/48 on the full horizon), so these rows
marginally understate the stack. The full horizon was measured serially only;
extrapolating D's parallel factor onto the 78.4 s at the top of this file puts a
pass near 20 seconds.

## 8. The search is not a multiplier here

A calibrated run costs one pass per step of the cycle-value search, so every
factor above is multiplied by the pass count. On this data it is not: the full
5,000-cycle budget of §5 is never reached (3,443 cycles spent), so `λ` stays at
0, and over 60 days both methods converge immediately with the recovery pass
skipped:

| Method | Passes | λ | Profit | Cycles |
| --- | --- | --- | --- | --- |
| cutting-plane | 1 | 0.0 | £12,956.53 | 175.7 |
| bisection | 1 | 0.0 | £12,956.53 | 175.7 |

Under the pro-rated budget of [`cycle-budget.md`](../cycle-budget.md) the budget
binds, the search spends several passes, and every factor above is multiplied by
that count.
