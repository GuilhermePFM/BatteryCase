# Pricing the cycle budget: two methods, measured

*Why the subproblem had to change before a second method was possible, and what
each method costs.*

[← README](../../README.md) · [model](model.md) · [cycle budget](../cycle-budget.md) ·
[architecture](../architecture.md) · [solve](../solve.md) · [validation](../validation.md)

---

§6 of the [write-up](model.md) describes two ways to find the charge `λ`
that rations a binding cycle budget: a bisection on cycle use, and Kelley's
cutting-plane method on the Lagrangian dual. Both are implemented
([architecture §4](../architecture.md#4-two-ways-to-price-the-cycle-budget)) and
both are selectable:

```bash
uv run battery-case dispatch --cycle-pricer bisection
uv run battery-case dispatch --cycle-pricer cutting-plane
uv run python scripts/compare_pricers.py 30        # every method on one instance
```

Everything below is measured by that script and by `tests/test_pricing.py`. One
*pass* means one full rolling run over the instance: 1,096 window MILPs on the
three-year horizon, about ten minutes. The pass count is what a method costs.

## 1. The subproblem had to change first

To price a constraint you must **remove** it from the subproblem: the charge
replaces the constraint, it does not accompany it. The windows did both. They
capped the cumulative cycle count *and* charged `λ` for it, so cycle use was
clipped at the budget by construction and the only thing a pass could report was
whether the clip was reached.

Measured on the three-day instance of `tests/test_pricing.py` (two modest days,
then a dear one, one cycle of budget), the same `λ` through both subproblems:

| λ (£/cycle) | capped: cycles | profit | subgradient | relaxed: cycles | profit | subgradient |
| --: | --: | --: | --: | --: | --: | --: |
| 0 | 1.000 | £1,435.79 | 0.000 | 3.000 | £2,027.34 | −2.000 |
| 100 | 1.000 | £1,435.79 | 0.000 | 3.000 | £2,027.34 | −2.000 |
| 300 | 1.000 | £1,435.79 | 0.000 | 1.000 | £1,435.79 | 0.000 |
| 400 | 1.000 | £1,435.79 | 0.000 | 1.000 | £1,435.79 | 0.000 |

The capped column is flat: **the subgradient is zero at every charge**. A
subgradient of zero reads as "already at the minimum", so a cutting-plane or
subgradient method handed that signal stops dead at `λ = 0`. The fault lies with
the signal rather than with bisection, which was the right tool for the one bit
it was given.

The relaxed column is a usable derivative. At `λ = 0` the horizon wants three
cycles against a budget of one, so the subgradient is −2: the charge is too low,
by a lot. At `λ = 300` cycle use is exactly 1.0 and the subgradient is 0, which
is the optimality condition. £300 is therefore the shadow price, where the
bisection's £1,435.55 is the top of a plateau
([cycle budget](../cycle-budget.md#what-the-search-is-searching-over)).

> [!WARNING]
> **The bound was also a cap.** Omitting `cycle_life_cap` from the block list
> used to change nothing at all, leaving the three-day answer at 1.000 cycles
> and £1,435.79, because `cycle_budget` was *also* the upper bound of every
> `n_cyc(t)` variable in `DispatchVariables.declare`. The row was the redundant
> copy, as §4.6 says, and the bound was doing the work. `n_cyc` is now declared
> without an upper bound, which makes `cycle_life_cap` the only place the budget
> is imposed and `blocks` a real relaxation lever.
> `tests/test_constraints.py` pins the free bound, and `tests/test_pricing.py`
> pins that a relaxed pass overspends.

## 2. What each method costs, against a known answer

Each instance is priced against a budget of **half** what the horizon spends
unpriced, so the cap binds hard. 30 days is small enough to solve whole, as one
capped MILP, which gives the comparison a ground truth the decomposition cannot
provide for itself.

### Three days, budget 1.0 cycle

| Method | Passes | λ | Profit | Bound | Certified? |
| --- | --: | --: | --: | --: | --- |
| exact (one MILP) | — | — | £1,435.79 | optimal | — |
| bisection | 13 | £1,435.55 | £1,435.79 | — | no |
| cutting planes | 3 | £675.79 | £1,435.79 | £1,435.79 | **yes, zero gap** |

### Seven days of real prices, budget 10.76 cycles

| Method | Passes | Wall clock | λ | Profit | vs exact | Bound | Gap |
| --- | --: | --: | --: | --: | --: | --: | --: |
| exact (one MILP) | — | 0.6 s | — | £1,133.62 | — | optimal | — |
| bisection | 13 | 3.4 s | £22.51 | £1,133.62 | 0.000% | — | — |
| cutting planes | 7 | 2.6 s | £22.66 | £1,131.23 | −0.211% | £1,133.63 | 0.008% |

### Thirty days of real prices, budget 43.65 cycles

| Method | Passes | Wall clock | λ | Profit | vs exact | Bound | Gap |
| --- | --: | --: | --: | --: | --: | --: | --: |
| exact (one MILP) | — | 3.9 s | — | £4,937.98 | — | optimal | — |
| bisection | 13 | 15.1 s | £28.47 | £4,937.33 | −0.013% | — | — |
| cutting planes | 7 | 10.3 s | £28.85 | £4,935.43 | −0.051% | £4,938.22 | 0.004% |

What these show:

- **The schedules are the same, to within a twentieth of a percent.** Cutting
  planes is not a profit improvement. On both real instances bisection's
  schedule is marginally *better*, by £0.65 on 30 days and £2.39 on seven,
  because it keeps the best pass it ever saw while the cutting-plane method
  recovers at the single `λ` its dual settled on.
- **The bound holds, and it is tight.** £4,938.22 against an exact £4,937.98
  puts the certificate 24p above the true optimum on 30 days, and 1p on seven.
  The 30-day run therefore *knows* it is within 0.05% without the ground-truth
  MILP that checked it here.
- **The pass count halves.** Seven passes against a fixed thirteen, so about
  1.3 h instead of 2.2 h on the three-year horizon, with a bound at the end of
  it.

### The pass count is a choice, not a constant

Bisection always spends `1 + 12`. The cutting-plane method stops on a measured
gap, so the tolerance buys the passes. On the 30-day instance:

| Tolerance | Passes | λ | Profit | Bound | Relative gap |
| --: | --: | --: | --: | --: | --: |
| 1e-2 | 5 | £34.75 | £4,859.03 | £4,947.90 | 0.498% |
| 1e-3 | 7 | £28.85 | £4,935.43 | £4,938.18 | 0.004% |
| 1e-4 | 7 | £28.85 | £4,935.43 | £4,938.18 | 0.004% |
| 1e-5 | 10 | £28.85 | £4,935.43 | £4,938.18 | 0.001% |

Five passes is too loose to quote: the gap is half a percent and the schedule
has given up 1.6% of profit. Seven is tight enough for any purpose here, and the
default `1e-4` lands there. The quoted figures move by pennies between runs,
because every pass is a MILP solved to a feasibility tolerance and a different
tie broken in one window shifts the last decimal of the dual.

## 3. Why the second method exists at all

None of the three reasons is profit:

1. **It reports quality.** Bisection returns a price and a schedule with no
   statement about either. `PricingResult.bound` is `None` for it, by type, so
   nothing downstream can quote a certificate it never computed.
2. **Its λ is interpretable.** £28.85 is the budget's shadow price, the marginal
   value of the last cycle. The bisection's answer is the top of a plateau,
   which yields the same schedule but is not a price to quote.
3. **It generalises to a vector.** §4.6 notes that a time-varying allowance
   `L̄(t)`, such as a per-year quota, is the case where the per-period and
   end-of-horizon forms of the cap stop being equivalent. That needs one
   multiplier per quota period: `g_y = B_y − (cycles spent in year y)` and the
   same master LP with `Y` columns. Bisection has no interval to halve there, so
   it cannot be extended to it at all.

## 4. Limits

- **A zero duality gap is a property of these instances.** Lagrangian
  relaxation of a mixed-integer program generally leaves a gap, and the method
  would then stop with a bracket it cannot close: still correct, less
  flattering. That both small instances closed to the penny says something about
  this problem's structure and nothing about the next one.
- **The bound rests on each pass being a true maximum.** Weak duality needs
  `L(λ)` maximised over the relaxed feasible set, and a rolling pass with one day
  of lookahead is a heuristic. It can under-solve and report a value *below* the
  true `L`, which would leave the bound no bound at all. The 30-day comparison is
  that check, and it held, twice. It has **not** been checked at 60 or 90 days,
  and should be before a bound is quoted on the three-year run.
- **Neither method fires on the headline run.** With the full 5,000-cycle budget
  of §5 the horizon spends 3,443, so the cap does not bind, `λ* = 0`, and both
  methods stop after a single pass, which `tests/test_pricing.py` asserts. All of
  this serves the pro-rated 1,500-cycle reading, and quotas.
- **The three-year priced run is still unmeasured.** At roughly ten minutes a
  pass it is hours of compute either way. The bound makes the ground-truth MILP
  that validated it at 30 days unnecessary; it does not make the pass cheaper.
