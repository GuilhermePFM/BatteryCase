# Tractability: one MILP, or a sequence of them?

§6 of [`model.md`](model.md) decomposes the horizon into rolling daily windows and
asserts that solving all 52,608 periods at once is not practical. This file holds
the measurements behind that assertion.

Everything here comes from [`scripts/solve_exact.py`](../../scripts/solve_exact.py),
which builds the formulation of §4 over the first *N* days and hands it to HiGHS
once, with no decomposition and no cycle value:

```
uv run python scripts/solve_exact.py <days> <time_limit_seconds>   # 0 days = the whole horizon
uv run python scripts/solve_exact.py 30 300 --csv docs/model/tractability.csv
```

`--csv` records the row in the table below, one row per window length; the whole
table is re-run by `make results` (stages `tractability` and `monolith`).

Measured on this machine (HiGHS 1.15.1 in process, single worker, 20 threads
available), on an otherwise idle machine. Raw numbers in
[`tractability.csv`](tractability.csv).

The solver settings are not uniform down this table, and deliberately so. The
tuning of
[`solver-parameter-tunning.md`](solver-parameter-tunning.md#they-apply-to-windows-only-and-the-cutoff-is-measured)
is measured on a 96-period window and only helps below a fortnight, so
`default_solver` applies it below that length and uses stock HiGHS at or above
it. The first four rows below are therefore tuned and the rest are stock — each
row solved by whichever configuration is faster at its own size.

## How solve time grows with the window

| Window | Periods | Binaries | Settings | Result | Solve time |
| --- | --- | --- | --- | --- | --- |
| 1 day | 48 | 48 | tuned | optimal | < 0.1 s |
| 2 days | 96 | 96 | tuned | optimal | 0.1 s |
| 4 days | 192 | 192 | tuned | optimal | 0.4 s |
| 7 days | 336 | 336 | tuned | optimal | 0.9 s |
| 14 days | 672 | 672 | stock | optimal | 9.7 s |
| 30 days | 1,440 | 1,440 | stock | optimal | 23.6 s |
| 60 days | 2,880 | 2,880 | stock | optimal | 173.2 s |

The growth is steep and not smooth, but the ratios are only readable *within* a
settings block, because the configuration changes at a fortnight. Among the
stock rows: 14 days to 30 doubles the time, and 30 to 60 multiplies it by
seven. Among the tuned rows: 4 days to 7 roughly doubles it. The 7-to-14 step
spans the cutoff and is **not** a growth measurement — 0.9 s and 9.7 s are two
different solvers.

Every window up to two months is proved optimal, the longest of them in under
three minutes, and 1,096 days is eighteen times further out than that.

> [!NOTE]
> **The 60-day cell was once unstable, and the cause was load.** An early run
> stopped this window at its 900 s limit with no proof and an incumbent of
> £12,948.07 — £7.40 below the optimum above. That run shared the machine with
> another job. Three subsequent runs on an idle machine all proved optimality,
> at 173.1 s, 173.0 s and 173.2 s. The instability was contention, not branch
> and bound finding a different route, which is why every timing on this page is
> now taken idle.

## The whole horizon in one program

Built as one MILP the problem is:

| | |
| --- | --- |
| Rows | 315,649 |
| Columns | 368,256 |
| Nonzeros | 1,052,159 |
| Binaries | 52,608 |
| Build time (pulp) | 2.2 s |
| After HiGHS presolve | 222,069 rows, 274,678 columns |

The model *fits*: assembling it takes 2.2 s and presolve handles it. Solving it is
the problem. Given an hour (HiGHS checked the limit between separation rounds and
stopped at 3,611 s):

| Elapsed | Best bound | Incumbent | Gap |
| --- | --- | --- | --- |
| 223 s | £216,421.31 | £203,365.53 | 6.42% |
| 1,559 s | £208,246.38 | £204,077.77 | 2.04% |
| 2,094 s | £208,166.65 | £204,077.77 | 2.00% |
| 3,087 s | £208,166.65 | £206,318.80 | 0.90% |
| **3,611 s (stopped)** | **£208,166.65** | **£206,318.80** | **0.90%** |

```
Status        Time limit reached
Primal bound  206318.795903
Dual bound    208166.653168
Gap           0.896% (tolerance: 0.01%)
Nodes         2
LP iterations 302844 (902 strong br., 52678 separation, 90175 heuristics)
```

`Nodes 2` is the striking part: in an hour the search **barely branched**. It
spent the first 2,100 s at the root, generating and re-generating tens of
thousands of cuts to drag the bound from £216,421 down to £208,167, where it
then stuck — the bound did not move again for the remaining 1,500 s. What did
move was the incumbent: at 3,087 s a sub-MIP heuristic found £206,318.80,
closing the gap from 2.00% to 0.90% in one step, and only then did the search
leave the root at all. Of 52,608 binaries, two nodes' worth were explored.

The shape of the hour is therefore: the bound is cheap to get close and then
immovable, and the remaining gap is an *incumbent* problem, not a bound
problem.

## What the comparison says

The rolling decomposition returns **£207,365.09**, in under three minutes of
1,096 small solves. That is *above* every incumbent the one-shot MILP found in
an hour, and below its best bound. What follows from that, and what does not:

**What is guaranteed.** Branch and bound maintains a *dual bound*: the best
objective achievable by any relaxation of the problem still in the tree. For a
maximisation the optimum can never exceed it, so the bound is an upper limit on
the MILP optimum rather than an estimate of it. Separately, the rolling plan
is feasible for the one-shot program: it satisfies every constraint of §4 over the
whole horizon (`assert_feasible` in `tests/helpers.py` re-derives them against the
saved plan), and evaluating the §3 objective expression on it reproduces
£207,365.09 exactly. A feasible point is a lower limit. The optimum of **this
model** is therefore bracketed, and with the run stopped at its limit the bracket
is:

```
£207,365.09  <=  model optimum  <=  £208,166.65
```

so the rolling plan is within **0.39%** of the optimum of this model. That is
an upper limit on what it gives up rather than a measured loss. It would not
narrow much further by waiting: the bound stopped moving at 2,094 s and spent
the last quarter of the hour flat.

**What is not guaranteed.** The bracket says nothing about the real world. It
bounds the optimum of the formulation, with its perfect price foresight,
price-taking battery, linear degradation and losses as specified in §4, and those
modelling choices are a far larger source of error than half a percent. The bound
is also only as sound as the solver's arithmetic: HiGHS works to finite
feasibility and integrality tolerances, so read it as £208,167 give or take solver
noise rather than to the penny. It is a bound on the *optimum*, not on what the
decomposition would lose on different data; nothing here shows the gap stays this
small on another three years of prices.

**The engineering conclusion does not depend on the bound.** Given a fixed hour
the one-shot solve returns a plan worth £1,046 less than the decomposition's,
0.50% worse, because branch and bound spends the hour proving things about the root
relaxation of a 368,000-variable problem rather than trading. The margin is
narrower than it once was — an earlier, contended run of the same solve stopped
£3,287 (1.6%) behind — so the honest reading is that the one-shot solve closes
much of the distance given a quiet machine, and still does not catch a
decomposition that takes under three minutes. The bound adds the reassurance
that what the decomposition leaves behind is small: at most 0.39% of the model
optimum, on this data.
