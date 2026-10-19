# Valuing the cycle budget: two methods, measured

*What the two methods need from the subproblem, and what each of them costs.*

[← README](../../README.md) · [model](model.md) · [cycle budget](../cycle-budget.md) ·
[architecture](../architecture.md) · [solve](../solve.md) · [validation](../validation.md)

---

§6 of the [write-up](model.md) describes two ways to find the cycle value `λ`
that rations a binding cycle budget: a bisection on cycle use, and Kelley's
cutting-plane method on the Lagrangian dual. Both are implemented
([architecture §4](../architecture.md#4-how-to-obtain-the-lagrangian-price-cutting-planes-and-bissection)) and
both are selectable:

```bash
uv run battery-case dispatch                         # cutting planes, the default
uv run battery-case dispatch --search bisection      # the reference method
uv run python scripts/compare_searches.py 30        # every method on one instance
uv run python scripts/sweep_searches.py            # every method, 1 to 90 days
uv run python scripts/sweep_searches.py 365 all --search cutting-plane --no-exact
uv run python scripts/tolerance_sweep.py 30         # what the tolerance buys, §2
```

Every table below is re-run by `make results` (`uv run python
scripts/reproduce_docs.py --list` for the stages one by one).

Everything below is measured by that script and by `tests/test_cycle_value.py`. One
*pass* means one full rolling run over the instance: 1,096 window MILPs on the
three-year horizon. What a pass *costs* depends on the instance — 44 s on the
calibrated three-year run below, 172 s on the headline run of
[§7](results.md), where nothing is priced out
([§2](#the-whole-horizon-with-no-truth-to-check-against)) — so the pass count is
what a method is compared on.

## 1. What a pass has to report

To value a constraint you must **remove** it from the subproblem: the cycle value
replaces the constraint, it does not accompany it. A window that caps the
cumulative cycle count *and* charges `λ` for it clips cycle use at the budget by
construction, so the only thing such a pass can report is whether the clip was
reached. That single bit is all bisection needs; it is not enough for a
cutting-plane method, which needs a value and a slope.

Measured on the three-day instance of `tests/test_cycle_value.py` (two modest days,
then a dear one, one cycle of budget), the same `λ` through both subproblems:

| λ (£/cycle) | capped: cycles | profit | subgradient | relaxed: cycles | profit | subgradient |
| --: | --: | --: | --: | --: | --: | --: |
| 0 | 1.000 | £894.29 | 0.000 | 3.000 | £2,027.34 | −2.000 |
| 100 | 1.000 | £894.29 | 0.000 | 3.000 | £2,027.34 | −2.000 |
| 300 | 1.000 | £1,435.79 | 0.000 | 1.000 | £1,435.79 | 0.000 |
| 400 | 1.000 | £1,435.79 | 0.000 | 1.000 | £1,435.79 | 0.000 |

The capped column spends exactly the budget at every charge, and
**the subgradient is zero at every one of them**. The profit does move — the
charge still redirects the cycle from the modest day to the dear one between
£100 and £300 — but that movement is invisible in the only signal the pass
reports. A
subgradient of zero reads as "already at the minimum", so a cutting-plane or
subgradient method handed that signal stops dead at `λ = 0`. The limitation is
in the signal, not in bisection, which asks only for the one bit a capped pass
can give.

The relaxed column is a usable derivative. At `λ = 0` the horizon wants three
cycles against a budget of one, so the subgradient is −2: the cycle value is too low,
by a lot. At `λ = 300` cycle use is exactly 1.0 and the subgradient is 0, which
is the optimality condition. £300 is therefore the shadow price, where the
bisection's £1,435.55 is the top of a plateau
([bisection](../bisection.md#what-the-search-is-searching-over)).

> [!IMPORTANT]
> **The budget must be a row and nothing else.** A relaxed pass only relaxes if
> dropping `cycle_life_cap` is the only thing that imposes the budget. Were
> `cycle_budget` *also* the upper bound of every `n_cyc(t)` variable in
> `DispatchVariables.declare` — which §4.6 notes is the cheaper-looking way to
> write the same feasible set — omitting the block would change nothing, the
> bound doing the work the row is supposed to do, and the relaxed column above
> would be identical to the capped one. So `n_cyc` is declared free, making
> `blocks` a real relaxation lever. `tests/test_constraints.py` pins the free
> bound, and `tests/test_cycle_value.py` pins that a relaxed pass overspends.

## 2. What each method costs, against a known answer

Each instance is calibrated against a budget of **half** what the horizon spends
at zero cycle value, so the cap binds hard. Every instance here is also solved whole, as one
capped MILP, which gives the comparison a ground truth the decomposition cannot
provide for itself — and lets the question "does the cutting-plane method
reproduce the bisection?" be asked against the right answer rather than against
the other method.

### The test instance: three days, budget 1.0 cycle

| Method | Passes | λ | Profit | Bound | Certified? |
| --- | --: | --: | --: | --: | --- |
| exact — one MILP | — | — | £1,435.79 | optimal | — |
| bisection | 13 | £1,435.55 | £1,435.79 | — | no |
| cutting planes | 3 | £675.79 | £1,435.79 | £1,435.79 | **yes — zero gap** |

### Real prices, horizon by horizon

The progression of [`tractability.csv`](tractability.csv), each horizon
calibrated against half of what it spends at zero cycle value, both methods on
the same instance, and
the capped program solved whole for a ground truth. Raw numbers in
[`cycle-value-sweep.csv`](cycle-value-sweep.csv), from
[`scripts/sweep_searches.py`](../../scripts/sweep_searches.py):

| Days | Budget | Exact profit | Bis passes | Bis λ | Bis profit | Cut passes | Cut λ | Cut profit | Cut bound | Cut gap | Cut − bis |
| --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| 1 | 1.83 | £131.45 | 13 | £11.28 | £131.45 | 7 | £11.33 | £130.10 | £131.45 | 0.000% | −1.03% |
| 2 | 3.29 | £310.41 | 13 | £18.80 | £310.41 | 9 | £18.82 | £309.23 | £310.41 | 0.000% | −0.38% |
| 4 | 6.24 | £576.26 | 13 | £21.48 | £575.55 | 9 | £21.52 | £575.55 | £576.26 | 0.000% | 0.00% |
| 7 | 10.76 | £1,133.62 | 13 | £22.51 | £1,133.62 | 7 | £22.66 | £1,131.23 | £1,133.63 | 0.008% | −0.21% |
| 14 | 19.67 | £2,190.84 | 13 | £24.71 | £2,176.81 | 8 | £24.49 | £2,176.81 | £2,190.88 | 0.008% | 0.00% |
| 30 | 43.65 | £4,937.98 | 13 | £28.47 | £4,937.33 | 7 | £28.85 | £4,935.43 | £4,938.22 | 0.004% | −0.04% |
| 60 | 87.83 | £11,948.07 | 13 | £30.81 | £11,945.75 | 9 | £29.86 | £11,936.95 | £11,948.60 | 0.005% | −0.07% |
| 90 | 133.03 | £17,592.35 | 13 | £36.77 | £17,592.95 | 9 | £36.17 | £17,577.53 | £17,594.31 | 0.006% | −0.09% |

**Cutting planes reproduces the bisection, and the agreement improves with the
horizon.** The one-day instance is its worst showing at −1.03%: with 48 periods
there is almost nothing to ration, so landing a few pence away in λ moves a
whole trade. From four days on the two plans differ by less than a
tenth of a percent, and twice — at 4 and 14 days — they are the same plan to
the penny. The charges agree throughout: £11.28 against £11.33 at one day,
£36.77 against £36.17 at ninety.

**The bound held in every row**, which is the column no bisection run can
produce. It sits above the best exactly solved objective in all eight
instances, by 1p at seven days and £1.96 at ninety — 0.011% of the answer at
90 days. The fairer comparison at that size is against HiGHS's *own* dual bound
on the same instance, since the 90-day one-shot solve no longer closes to zero
gap: £4,938.19 at 30 days and £17,594.04 at 90, so the Lagrangian bound is
within 3p and 27p of what the monolith proves, without ever building the
monolith.

**And it is consistently cheaper.** Thirteen passes against seven to nine — a
mean of 8.1 across the sweep — and lower wall clock in every row: 24.9 s against
32.9 s at ninety days, 6.9 s against 11.1 s at thirty.

> [!NOTE]
> Two artefacts of reading these numbers honestly. The 2- and 4-day gaps come
> out marginally *negative* (order 1e-9): the master LP's envelope minimum is
> computed to a tolerance, so it can land a hair above the best evaluated `L`.
> And every row here has a proven exact answer, including 60 and 90 days, and it
> is reached faster at 60 days than the *unconstrained* window of the same
> length in [`tractability.md`](tractability.md) — 66 s against 173 s — and at
> 90 days it is reached at all, which that table never attempts. Not a
> contradiction but a different instance: a cycle budget *halved* against use at
> zero cycle value is itself a strong constraint, and it prunes the search that
> the unconstrained window leaves open. It does not make the instance cheap:
> the 90-day capped solve still takes 161 s and stops at a 0.010% gap rather
> than a proof.

### The whole horizon, with no truth to check against

The sweep above stops at 90 days because that is as far as a one-shot MILP will
go, and the exact column is what gives those rows their value. Cutting planes on
its own goes the rest of the way, each horizon still calibrated against half of what
it spends at zero cycle value. Raw numbers in
[`cycle-value-long-horizons.csv`](cycle-value-long-horizons.csv), from
`scripts/sweep_searches.py 180 365 all --search cutting-plane --no-exact`:

| Days | Periods | Budget | Passes | λ | Profit | Bound | Dual gap | Bound − profit | Wall clock | Per pass |
| --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| 180 | 8,640 | 258.95 | 9 | £39.04 | £30,515.91 | £30,594.49 | 0.005% | 0.26% | 52.9 s | 5.9 s |
| 365 | 17,520 | 483.39 | 9 | £42.33 | £60,156.89 | £60,423.98 | 0.007% | 0.44% | 99.5 s | 11.1 s |
| 1,096 | 52,608 | 1,721.30 | 10 | £30.19 | £184,021.30 | £187,234.28 | 0.003% | 1.72% | 439.6 s | 44.0 s |

**The pass count does not grow with the horizon.** Nine passes at 180 and 365
days and ten over three years, against the seven to nine the 1-to-90-day rows
spend. Bisection's 13 is a constant as well, so its 1.5× stays 1.5×: roughly 17
minutes against 13 on the full horizon.

**A pass costs about 44 seconds on this instance.** Three years prices in
7 min 20 s end to end, ten passes. Per window MILP that is 0.040 s over three
years against 0.030–0.033 s at 180 and 365 days: the cost is near enough linear
in the horizon, with the full run a third again as dear per window. That last
part is measured, not explained. The figure is specific to a *binding* budget:
at `λ ≈ £30` most marginal trades are priced out and each window MILP is easy.
The headline run of [§7](results.md), on the full 5,000-cycle budget where
`λ = 0`, spends 172.4 s on the same 1,096 windows — 0.157 s each, nearly four
times dearer. A pass is the unit of *count*, not a fixed quantity of time.

**The dual converges; the deliverable plan drifts.** The gap column holds at
0.003–0.007%, which is the master LP closing on λ, and it is not the interesting
column here. The distance from the bound to the *feasible* plan is: 0.10% at
90 days, 0.26% at 180, 0.44% at 365, 1.72% over three years — £3,213 between
£184,021.30 and £187,234.28. Whether that is the recovery pass giving up profit
or the bound being loose cannot be separated without a proven optimum, and none
exists at this size. The honest statement is the weaker one the certificate
actually supports: on the three-year instance this plan is within 1.72% of
anything the relaxation admits.

> [!NOTE]
> This is still not the headline instance. The budget here is half of at zero cycle value
> use, 1,721 cycles over three years, which is why λ is £30.19. Under §5's
> 5,000-cycle budget the cap does not bind at all and both methods stop after a
> single pass.

### The pass count is a choice, not a constant

Bisection always spends `1 + 12`. The cutting-plane method stops on a measured
gap, so the tolerance buys the passes. On the 30-day instance, from
[`scripts/tolerance_sweep.py`](../../scripts/tolerance_sweep.py), raw numbers in
[`cycle-value-tolerance.csv`](cycle-value-tolerance.csv):

| Tolerance | Passes | λ | Profit | Bound | Relative gap |
| --: | --: | --: | --: | --: | --: |
| 1e-2 | 5 | £34.75 | £4,859.03 | £4,947.95 | 0.498% |
| 1e-3 | 7 | £28.85 | £4,935.43 | £4,938.22 | 0.004% |
| 1e-4 | 7 | £28.85 | £4,935.43 | £4,938.22 | 0.004% |
| 1e-5 | 10 | £28.85 | £4,935.43 | £4,938.22 | 0.001% |

Five passes is too loose to quote: the gap is half a percent and the plan
has given up 1.6% of profit. Seven is tight enough for any purpose here, and the
default `1e-4` lands there. The quoted figures move by pennies between runs,
because every pass is a MILP solved to a feasibility tolerance and a different
tie broken in one window shifts the last decimal of the dual.

## 3. Why cutting planes is the default

None of the three reasons is profit:

1. **It reports quality.** Bisection returns a price and a plan with no
   statement about either. `DualSearchResult.bound` is `None` for it, by type, so
   nothing downstream can quote a certificate it never computed.
2. **Its λ is interpretable.** £28.85 is the budget's shadow price, the marginal
   value of the last cycle. The bisection's answer is the top of a plateau,
   which yields the same plan but is not a price to quote.
3. **It generalises to a vector.** §4.6 notes that a time-varying allowance
   `L̄(t)`, such as a per-year quota, is the case where the per-period and
   end-of-horizon forms of the cap stop being equivalent. That needs one
   multiplier per quota period: `g_y = B_y − (cycles spent in year y)` and the
   same master LP with `Y` columns. Bisection has no interval to halve there, so
   it cannot be extended to it at all.

## 4. Limits

- **A near-zero duality gap is a property of these instances.** Lagrangian
  relaxation of a mixed-integer program generally leaves a gap, and the method
  would then stop with a bracket it cannot close: still correct, less
  flattering. That eight instances closed to within 0.01% says something about
  this problem's structure and nothing about the next one.
- **The bound rests on each pass being a true maximum.** Weak duality needs
  `L(λ)` maximised over the relaxed feasible set, and a rolling pass with one day
  of lookahead is a heuristic. It can under-solve and report a value *below* the
  true `L`, which would leave the bound no bound at all. The sweep above is that
  check, and the bound held above the proven optimum in all eight rows — 1 to 90
  days. That is as far as it is *checked*: the 180-day, 365-day and three-year
  rows have no proven optimum to check against, so their bounds rest on the pass
  being a true maximum rather than on evidence.
- **Neither method fires on the headline run.** With the full 5,000-cycle budget
  of §5 the horizon spends 3,443, so the cap does not bind, `λ* = 0`, and both
  methods stop after a single pass, which `tests/test_cycle_value.py` asserts. All of
  this serves the pro-rated 1,500-cycle reading, and quotas.
- **The three-year calibrated run has no ground truth.** It is measured — 10
  passes, 7 min 20 s, λ = £30.19 — but the exact MILP that validated the bound
  at 30 days cannot be built at this size, so nothing independent confirms the
  £184,021.30. The bound is what stands in for it, and it is 1.72% away.
