# Analysis on solver time

[← README](../../README.md) · [model](model.md) · [solve](../solve.md) ·
[tractability](tractability.md) · [cycle budget](../cycle-budget.md) ·
[validation](../validation.md)

---

[`tractability.md`](tractability.md) measures the choice between one MILP and a
sequence of them. This file measures the sequence itself: one pass of
`RollingPolicy` over the three-year horizon — 1,096 window MILPs of 96 periods,
48 committed and 48 of lookahead — and asks what the 450 seconds are made of.

Every number below keeps the binaries of §4.3 in the model. Nothing here
relaxes the mode exclusivity or drops a constraint block; the comparisons are
between ways of *solving* the same formulation, except where a window geometry
is varied, which is marked as such.

HiGHS 1.15.1 in process via pulp 4.0.1, 20 cores
available, one `HiGHS` object reused across every window as the loop already
does.

## The settings that came out fastest

```python
pulp.HiGHS(msg=False, mip_heuristic_run_rens=False, mip_allow_restart=False)
```

Full three-year horizon, against the £207,365.00 that
[`tractability.md`](tractability.md#what-the-comparison-says) brackets:

| | Seconds | Speed-up | Profit | Cycles |
| --- | --- | --- | --- | --- |
| baseline 48/48, default solver | 450.5 | 1.00× | £207,365.04 | 3,443.0 |
| 48/48, no RENS + no restart | 217.7 | **2.07×** | £207,365.07 | 3,442.6 |
| 48/24, no RENS + no restart | 97.0 | **4.64×** | £207,365.17 | 3,442.6 |

Both settings are free: the profit moves by £0.03 and £0.13, in the *same*
direction as the baseline's own solver noise. 

No gap tolerance is needed. An earlier configuration using `gapAbs = 0.5`
reached 111.7 s at a cost of £5.22; turning RENS off instead reaches 97.0 s and
gains £0.13, so the tolerance knob is strictly dominated here.

## 1. The breakdown of one window

Instrumenting pulp's four solve stages over 40 windows of the horizon:

| Stage | Per window |
| --- | --- |
| `build_problem` (pulp model assembly) | 4.2 ms |
| `buildSolverModel` (pulp → HiGHS transfer) | 1.7 ms |
| `callSolver` (HiGHS) | **120.2 ms** |
| `findSolutionValues` (reading values back) | 0.7 ms |

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

The root LP starts 3.46% high; the finished root is 0.018% high, which is at the
default termination tolerance once a matching incumbent exists. Nothing is left
to branch on.

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

The root reaches a 0.06% gap at 0.1 s and 322 iterations. The remaining 70% of
the solve is seven sub-MIP heuristic calls and one restart. 911 of the 1,296 LP
iterations are heuristics.

## 3. The solver options, swept

100 consecutive windows, 3 interleaved repetitions, median reported.
Run-to-run spread was 1.9–4.2 ms against effects of ~46 ms, so the ordering is
reproducible.

| Config | ms/window | Speed-up | Objective |
| --- | --- | --- | --- |
| baseline | 135.62 | 1.00× | — |
| **`mip_heuristic_run_rens = false`** | **89.03** | **1.52×** | **−0.0001%** |
| `mip_heuristic_run_rins = false` | 101.19 | 1.34× | −0.0000% |
| no RENS + no RINS | 94.64 | 1.43× | −0.0003% |
| **no RENS + `mip_allow_restart = false`** | **88.25** | **1.54×** | **−0.0000%** |
| no RENS + no RINS + no restart | 88.58 | 1.53× | −0.0002% |

RENS is the sub-MIP heuristic the log charges 0.15 s of 0.21 s to. With the root
bound already at the optimum (§2), it is searching for an incumbent the cheap
`root_reduced_cost` heuristic has usually already found.

Removing RINS **as well** is reproducibly *slower* than removing RENS alone
(1.43× against 1.52×, in all three repetitions). The two do not compose: with
both gone the solver loses the incumbent that lets it terminate.

### Settings that backfire

100 windows, single run, measured on top of no-RENS + no-RINS:

| | Speed-up | Objective |
| --- | --- | --- |
| `mip_lifting_for_probing = 0` | **0.43×** | −0.0223% |
| `mip_heuristic_run_root_reduced_cost = false` | 1.20× | −0.0006% |
| `presolve = off` | 1.37× | −0.0005% |

Probing lifting is load-bearing for the bound, consistent with cuts doing all
the work: switching it off more than doubles the solve time.

### Settings that do nothing

Within ±2%, inside run-to-run noise: `mip_detect_symmetry`,
`mip_heuristic_effort`, `mip_heuristic_run_feasibility_jump`,
`mip_lp_age_limit`, `mip_pool_age_limit`, `mip_max_cutpool_age`,
`mip_max_start_nodes`, `mip_root_presolve_only`, `simplex_strategy`.

### The gap tolerances

80–100 windows, single run:

| | ms/window | Total objective | Worst single window |
| --- | --- | --- | --- |
| `gapAbs = 1.0` (£) | 79.2 | −0.0031% | −0.161% |
| `gapRel = 1e-3` | 90.9 | −0.0133% | −0.100% |
| `gapRel = 1e-2` | 62.7 | −0.1758% | −0.981% |
| no RENS + no RINS + no restart + `gapAbs = 0.5` | 77.5 | −0.0182% | −0.161% |

An absolute gap behaves better than a relative one at this scale: a window's
objective is only £200–400, so one `gapRel` means a different amount of
absolute slack in every window of the horizon. Superseded by the no-RENS result
above, which is both faster on a full pass and free.

## 4. Approaches that did not pay

### Warm starts

Consecutive windows overlap by 48
periods, so window *i* was seeded with window *i−1*'s solution shifted by 48 —
every variable of §2 including the binary — and solved with pulp's
`warmStart=True`, which hands the point to HiGHS as `setSolution`:

| | Per window | Committed profit, 80 windows |
| --- | --- | --- |
| `warmStart=False` | 142.7 ms | £17,387.59 |
| `warmStart=True` | 143.8 ms | £17,387.59 |

No gain. §2 is why: with a node count of 1 there is no tree to prune, and an
incumbent handed in at the start does not spare the root its separation rounds.

### Solving the LP first

If the LP relaxation were usually integral, a window could be settled by one LP
and the MILP called only when it is not. Over 120 windows:

| | |
| --- | --- |
| LP solve | 5.2 ms |
| MILP solve | 141.6 ms (27.4×) |
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
rows and 96 columns were never solved over.

## 5. Window geometry

Solve time grows superlinearly in the window length
([`tractability.md`](tractability.md#how-solve-time-grows-with-the-window)), so
shortening the lookahead pays more than proportionally. First 150 days, default
solver settings:

| commit / lookahead (periods) | Windows | Seconds | ms/window | Profit | vs 48/48 |
| --- | --- | --- | --- | --- | --- |
| 48 / 48 (as shipped) | 150 | 31.96 | 213.1 | £29,346.81 | baseline |
| 48 / 36 | 150 | 20.82 | 138.8 | £29,346.84 | +0.000% |
| **48 / 24** | 150 | **12.56** | 83.7 | £29,346.82 | **+0.000%** |
| 48 / 12 | 150 | 10.22 | 68.1 | £29,344.37 | −0.008% |
| 48 / 72 | 150 | 46.00 | 306.7 | £29,346.84 | +0.000% |
| 24 / 24 | 300 | 15.10 | 50.3 | £29,346.84 | +0.000% |
| 24 / 48 | 300 | 32.11 | 107.0 | £29,346.84 | +0.000% |
| 96 / 24 | 75 | 22.30 | 297.3 | £29,346.84 | +0.000% |
| 96 / 48 | 75 | 29.84 | 397.9 | £29,346.84 | +0.000% |
| 144 / 48 | 50 | 44.27 | 885.3 | £29,346.84 | +0.000% |

Twelve hours of foresight buys everything a full day of it does. Profit is flat
to the penny across almost the whole grid, which is
[`solve.md`](../solve.md#is-one-day-of-foresight-enough)'s observation from the
other side — committing a whole week at a time earns exactly the same as
committing a day. A 4 MWh store carries at most two hours of discharge across a
boundary, so no decision in a window reaches 24 periods past it.

Holding the lookahead fixed, the commit length buys nothing: `24/48`, `48/48`,
`96/48` and `144/48` all return the same profit while the per-window cost rises
from 107 ms to 885 ms.

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

First 150 days, `spawn` processes, serial reference in the same run, default
solver settings:

| | Seconds | Speed-up | Profit | vs serial |
| --- | --- | --- | --- | --- |
| serial | 30.96 | 1.00× | £29,346.81 | baseline |
| K = 5 | 11.17 | 2.77× | £29,370.31 | +0.080% |
| K = 10 | 9.71 | 3.19× | £29,335.90 | −0.037% |
| K = 15 | 7.48 | 4.14× | £29,345.99 | −0.003% |

The drift is not monotonic in *K* and changes sign — K = 5 came out £23 *ahead*
of the serial pass — so it is boundary noise rather than a cost of chunking. The
speed-up falls short of *K* because each spawned worker re-imports and re-reads
both spreadsheets, and because chunks differ in difficulty, so the pass ends
with the slowest one.

**`fork` does not work.** `ProcessPoolExecutor` defaults to it on Linux, and
forking after a `Highs` object has been constructed in the parent leaves the
workers spinning at 100% CPU indefinitely — five workers burned 22 minutes of
CPU each with no progress and had to be killed. `mp.get_context("spawn")` avoids
it; every parallel number above is from spawn.

## 7. The three stacked

First 150 days, each row adding to the one above, one process tree on an
otherwise idle machine:

| | Seconds | Speed-up | Profit | vs A |
| --- | --- | --- | --- | --- |
| **A** baseline 48/48, default solver | 30.83 | 1.00× | £29,346.81 | baseline |
| **B** A + lookahead 24 | 11.67 | 2.64× | £29,346.82 | +0.0001% |
| **C** B + no restart + `gapAbs = 0.5` | 8.62 | 3.58× | £29,346.42 | −0.0013% |
| **D** C + 15-way chunk parallel | 4.25 | **7.25×** | £29,345.42 | −0.0047% |

C and D predate the no-RENS result of §3 and were not re-run with it; on the
full horizon the §3 settings beat C's by 111.7 s → 97.0 s at no cost in profit,
so these two rows understate what the stack reaches. The full horizon was
measured serially only; extrapolating D's parallel factor onto the 97.0 s at the
top of this file puts a pass near 30 seconds.

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
