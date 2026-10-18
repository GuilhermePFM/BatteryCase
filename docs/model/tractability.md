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
available). Raw numbers in [`tractability.csv`](tractability.csv).

## How solve time grows with the window

| Window | Periods | Binaries | Result | Solve time |
| --- | --- | --- | --- | --- |
| 1 day | 48 | 48 | optimal | < 0.1 s |
| 2 days | 96 | 96 | optimal | 0.2 s |
| 4 days | 192 | 192 | optimal | 1.7 s |
| 7 days | 336 | 336 | optimal | 3.4 s |
| 14 days | 672 | 672 | optimal | 5.0 s |
| 30 days | 1,440 | 1,440 | optimal | 30.1 s |
| 60 days | 2,880 | 2,880 | **time limit, no proof** | 900 s, stopped |

The growth is steep and not smooth. 14 days is only half again as slow as 7, and
30 days is six times slower than 14. The cliff for this formulation sits between
30 and 60 days: a two-month window could not be proved optimal in fifteen minutes.
1,096 days is thirty-six times further out than the last window that solved.

## The whole horizon in one program

Built as one MILP the problem is:

| | |
| --- | --- |
| Rows | 315,649 |
| Columns | 368,256 |
| Nonzeros | 1,052,159 |
| Binaries | 52,608 |
| Build time (pulp) | 2.4 s |
| After HiGHS presolve | 223,429 rows, 276,038 columns |

The model *fits*: assembling it takes 2.4 s and presolve handles it. Solving it is
the problem. Given an hour (HiGHS checked the limit between separation rounds and
stopped at 3,812 s):

| Elapsed | Best bound | Incumbent | Gap |
| --- | --- | --- | --- |
| 358 s | £211,477.28 | £203,312.32 | 4.02% |
| 637 s | £208,969.71 | £203,312.32 | 2.78% |
| 957 s | £208,571.57 | £204,077.77 | 2.20% |
| 1,755 s | £208,299.01 | £204,077.77 | 2.07% |
| **3,812 s (stopped)** | **£208,209.57** | **£204,077.77** | **2.02%** |

```
Status        Time limit reached
Primal bound  204077.765048
Dual bound    208209.567474
Gap           2.02% (tolerance: 0.01%)
Nodes         0
LP iterations 210520 (49853 separation)
```

`Nodes 0` is the striking part: in an hour the search **never branched**. It spent
the whole hour at the root, generating and re-generating tens of thousands of cuts
to drag the bound down from £211,477 to £208,210, and the last 2,000 s of that
bought 0.18 percentage points. The 52,608 binaries were never explored at all.

## What the comparison says

The rolling decomposition returns **£207,365.00**, in minutes of 1,096 small
solves. That is *above* every incumbent the one-shot MILP found in an hour, and
below its best bound. What follows from that, and what does not:

**What is guaranteed.** Branch and bound maintains a *dual bound*: the best
objective achievable by any relaxation of the problem still in the tree. For a
maximisation the optimum can never exceed it, so the bound is an upper limit on
the MILP optimum rather than an estimate of it. Separately, the rolling plan
is feasible for the one-shot program: it satisfies every constraint of §4 over the
whole horizon (`assert_feasible` in `tests/helpers.py` re-derives them against the
saved plan), and evaluating the §3 objective expression on it reproduces
£207,365.00 exactly. A feasible point is a lower limit. The optimum of **this
model** is therefore bracketed, and with the run stopped at its limit the bracket
is:

```
£207,365.00  <=  model optimum  <=  £208,209.57
```

so the rolling plan is within **0.41%** of the optimum of this model. That is
an upper limit on what it gives up rather than a measured loss, and it would
narrow further had the bound kept falling.

**What is not guaranteed.** The bracket says nothing about the real world. It
bounds the optimum of the formulation, with its perfect price foresight,
price-taking battery, linear degradation and losses as specified in §4, and those
modelling choices are a far larger source of error than half a percent. The bound
is also only as sound as the solver's arithmetic: HiGHS works to finite
feasibility and integrality tolerances, so read it as £208,210 give or take solver
noise rather than to the penny. It is a bound on the *optimum*, not on what the
decomposition would lose on different data; nothing here shows the gap stays this
small on another three years of prices.

**The engineering conclusion does not depend on the bound.** Given a fixed hour
the one-shot solve returns a plan worth £3,287 less than the decomposition's,
1.6% worse, because branch and bound spends the hour proving things about the root
relaxation of a 368,000-variable problem rather than trading. The bound adds the
reassurance that what the decomposition leaves behind is small: at most 0.41% of
the model optimum, on this data.
