# Tractability: one MILP, or a sequence of them?

§6 of [`model.md`](model.md) decomposes the horizon into rolling daily windows and
asserts that solving all 52,608 periods at once is not practical. This file is the
measurement behind that assertion, and the comparison it is worth keeping.

Everything here comes from [`scripts/solve_monolith.py`](../../scripts/solve_monolith.py),
which builds the formulation of §4 over the first *N* days and hands it to HiGHS
once, with no decomposition and no cycle pricing:

```
uv run python scripts/solve_monolith.py <days> <time_limit_seconds>   # 0 days = the whole horizon
```

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

The growth is steep and not smooth — 14 days is only half again as slow as 7, then
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

So the model *fits* — assembling it is trivial and presolve handles it. Solving it
is the problem. (Run in progress; final status recorded below when the hour expires.)

| Elapsed | Best bound | Incumbent | Gap |
| --- | --- | --- | --- |
| 358 s | £211,477.28 | £203,312.32 | 4.02% |
| 637 s | £208,969.71 | £203,312.32 | 2.78% |
| 957 s | £208,571.57 | £204,077.77 | 2.20% |
| 1,057 s | £208,492.45 | £204,077.77 | 2.16% |

Through all of this the search is still at the **root node** — zero nodes
processed, tens of thousands of cuts generated and re-generated. It has not begun
to branch on 52,608 binaries.

## What the comparison says

The rolling decomposition returns **£207,365.00**, in minutes of 1,096 small
solves. That is *above* every incumbent the one-shot MILP found in the first
twenty minutes, and below its best bound. Two things follow, and it is worth being
precise about how much each one is worth.

**What is guaranteed.** Branch and bound maintains a *dual bound*: the best
objective achievable by any relaxation of the problem still in the tree. For a
maximisation the optimum can never exceed it, so the bound is an upper limit on
the MILP optimum, not an estimate of it. Separately, the rolling schedule is
feasible for the one-shot program — it satisfies every constraint of §4 over the
whole horizon (`assert_feasible` in `tests/helpers.py` re-derives them against the
saved schedule), and evaluating the §3 objective expression on it reproduces
£207,365.00 exactly. A feasible point is a lower limit. So the optimum of **this
model** is bracketed:

```
£207,365.00  <=  model optimum  <=  best bound at the time of writing
```

The bound is still falling as cuts tighten the relaxation, so the bracket narrows
with the run and the figures below are a snapshot, not a converged answer. At
1,246 s the bound stood at £208,433.72, putting the rolling schedule within 0.51%
of the optimum.

**What is not guaranteed.** The bracket says nothing about the real world. It
bounds the optimum of the formulation — perfect price foresight, a price-taking
battery, linear degradation, losses as specified in §4 — and the modelling choices
behind those are a far larger source of error than half a percent. The bound is
also only as sound as the solver's arithmetic: HiGHS works to finite feasibility
and integrality tolerances, so read it as £208,434 give or take solver noise, not
to the penny. And it is a bound on the *optimum*, not on what the decomposition
would lose on different data: nothing here shows the gap stays this small on
another three years of prices.

**The engineering conclusion does not depend on the bound at all.** Given a fixed
quarter of an hour the one-shot solve returns a *worse* schedule (£204,077.77)
than the decomposition does, because branch and bound spends that budget proving
things about a 368,000-variable tree rather than trading. The bound then adds the
reassurance that what the decomposition leaves behind is small — at most about
half a percent of the model optimum, on this data.
