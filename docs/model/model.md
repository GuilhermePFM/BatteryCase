# Battery dispatch model

Formulation of the battery dispatch problem for the Aurora second-round
technical exercise: battery trading across two wholesale
electricity markets over 2018–2020, as a price taker.

---

## 1. Problem statement

We maximize revenue, a battery buys energy (charges) when prices are low and sells (discharge) when they are high. Two
wholesale markets are available, quoted in £/MWh and settled at different time
resolutions, and the battery may split its power between them. The objective is
to choose a charge/discharge schedule that maximises profit over the horizon.

The battery is a **price taker**: its own actions do not move either market's
prices, so the price series are exogenous inputs.

The problem is posed as a mixed-integer linear program on a **common half-hourly
grid**. Market 1 settles natively at that resolution; Market 2 settles hourly,
and is represented by holding its decision variables constant across the two
half hours of each hour.

## 2. Notation

### Sets and indices

| Symbol | Meaning |
| --- | --- |
| $t \in \mathcal{T}$ | half-hourly settlement period, $t = 1, \dots, T$ |
| $h \in \mathcal{H}$ | trading hour |
| $\mathcal{T}_h$ | the two half-hourly periods making up hour $h$ |
| $m \in \{1, 2\}$ | market |

### Parameters

| Symbol | Value | Unit | Meaning |
| --- | --- | --- | --- |
| $\Delta t$ | 0.5 | h | length of a settlement period |
| $p_1(t)$ | — | £/MWh | Market 1 price in period $t$ (half-hourly) |
| $p_2(t)$ | — | £/MWh | Market 2 price in period $t$ (hourly, held across $\mathcal{T}_h$) |
| $\overline{C}$ | 2 | MW | maximum charge rate, across both markets |
| $\overline{D}$ | 2 | MW | maximum discharge rate, across both markets |
| $\overline{S}_{\max}$ | 4 | MWh | nominal storage volume, before degradation |
| $e_c$ | 0.05 | – | fraction of imported energy lost before storage |
| $e_d$ | 0.05 | – | fraction of discharged energy lost before reaching the grid |
| $\overline{L}$ | 5000 | cycles | cycle life |
| $\rho$ | $10^{-5}$ | /cycle | storage volume lost per equivalent full cycle |

Parameter values are from Attachment 1. The spreadsheet quotes the degradation
rate in percent (0.001 %/cycle), so $\rho = 10^{-5}$ as a fraction. 

### Decision variables

| Symbol | Domain | Unit | Meaning |
| --- | --- | --- | --- |
| $c_1(t)$ | $\geq 0$ | MW | charging power bought from Market 1 |
| $c_2(t)$ | $\geq 0$ | MW | charging power bought from Market 2 |
| $d_1(t)$ | $\geq 0$ | MW | discharging power drawn from storage for Market 1 |
| $d_2(t)$ | $\geq 0$ | MW | discharging power drawn from storage for Market 2 |
| $S(t)$ | $\geq 0$ | MWh | energy stored |
| $u(t)$ | binary | – | 1 when charging, 0 when discharging |
| $S_{\max}(t)$ | $\geq 0$ | MWh | effective storage volume in period $t$, after degradation |
| $n_{\text{cyc}}(t)$ | $\geq 0$ | cycles | equivalent full cycles accumulated up to period $t$ |

The two sides are measured at different points. $c_m$ is power **imported from
the grid**, of which $(1 - e_c)\,c_m$ reaches storage. $d_m$ is power **drawn
from storage**, of which $(1 - e_d)\,d_m$ reaches the grid — so the store is
debited the full $d_m$ in §4.2, while only $(1 - e_d)\,d_m$ is paid for in §3.
Each rate limit in §4.3 caps its own variable directly, both being treated as
capabilities of the battery.

$n_{\text{cyc}}(t)$ counts whole cycles physically, but is left continuous
rather than integer: rounding it up would be conservative and costs an integer
variable in an already large model.

## 3. Objective

Maximise total profit over the horizon. Revenue in a period is the energy
delivered to each market at that market's price, less the energy bought; the
factor $\Delta t = \tfrac{1}{2}$ converts power in MW to energy in MWh over the
half-hourly period. Only $(1 - e_d)$ of the power drawn from storage reaches
the grid, and only that part is paid for.

$$
\max \sum_{t \in \mathcal{T}} R(t)
$$

where

$$
\begin{aligned}
R(t) &= \frac{p_1(t) (1 - e_d) d_1(t) + p_2(t) (1 - e_d) d_2(t) - p_1(t) \cdot c_1(t) - p_2(t) \cdot c_2(t)}{2} \\[4pt]
     &= \frac{p_1(t)\,\bigl((1 - e_d)\,d_1(t) - c_1(t)\bigr) + p_2(t)\,\bigl((1 - e_d)\,d_2(t) - c_2(t)\bigr)}{2}
\end{aligned}
$$

## 4. Constraints

### 4.1 Storage bounds

Stored energy stays between empty and the effective storage volume, which is
itself a variable, and shrinks over the horizon as the battery degrades (§4.7).

$$
0 \leq S(t) \leq S_{\max}(t) \qquad \forall t \in \mathcal{T}
$$

### 4.2 Energy balance

Energy stored carries from one period to the next, increased by what is charged
and reduced by what is discharged in that period. The factor $\Delta t$
converts power in MW to energy in MWh over the half-hourly period, matching the
objective.

Charging is lossy: a fraction $e_c$ of what is imported from the grid is lost
before it reaches storage, so only $(1 - e_c)\,(c_1 + c_2)$ is stored.
Discharging debits the store by the full $d_1 + d_2$, since $d_m$ is defined at
the storage side; the discharge loss is taken in §3, where only
$(1 - e_d)\,d_m$ is paid for.

$$
S(t) = S(t-1) + \Delta t \,\bigl[ (1 - e_c)\bigl(c_1(t) + c_2(t)\bigr) - d_1(t) - d_2(t) \bigr] \qquad \forall t \in \mathcal{T}
$$

with the battery starting empty:

$$
S(0) = 0
$$

The round-trip efficiency is $(1 - e_c)(1 - e_d) = 0.9025$, so a price spread
of about 11% is needed before a cycle breaks even.

### 4.3 Complementarity Constraint: charge or discharge, not both

A binary $u(t)$ makes charging and discharging mutually exclusive, and
simultaneously imposes the rate limits across both markets.

$$
\begin{aligned}
0 \leq c_1(t) + c_2(t) &\leq \overline{C} \cdot u(t) \\[4pt]
0 \leq d_1(t) + d_2(t) &\leq \overline{D} \cdot \bigl(1 - u(t)\bigr) \\[4pt]
c_1(t),\; c_2(t),\; d_1(t),\; d_2(t) &\geq 0
\end{aligned}
$$

When $u(t) = 1$ the battery may charge and all discharge is forced to zero;
when $u(t) = 0$ the reverse.

Both rates are read as capabilities of the battery itself, so each caps its own
variable directly and no efficiency factor appears here. The discharge limit
therefore bounds the power drawn from storage, and the most the battery can
deliver to the grid in a period is $(1 - e_d)\overline{D} = 1.9$ MW.

### 4.4 Capacity constraints

Charging is limited by the headroom remaining in the store, and discharging by
what the store holds.

$$
\begin{aligned}
\Delta t \,(1 - e_c)\bigl(c_1(t) + c_2(t)\bigr) &\leq S_{\max}(t) - S(t-1) \\[4pt]
\Delta t \,\bigl(d_1(t) + d_2(t)\bigr) &\leq S(t-1)
\end{aligned}
$$

Both are implied by the storage bounds of §4.1 together with the balance of
§4.2, so they are redundant; they are stated because they make explicit what
the bounds enforce only indirectly.

### 4.5 Market 2 hourly commitment

Capacity committed to Market 2 is held for that market's entire hourly
interval. This applies to selling as much as to buying, so both of its decision
variables are constant across the two half hours of each hour.

$$
\begin{aligned}
c_2(t_1) &= c_2(t_2) \\[4pt]
d_2(t_1) &= d_2(t_2)
\end{aligned}
\qquad \forall\, t_1, t_2 \in \mathcal{T}_h,\ \ \forall h \in \mathcal{H}
$$

Market 1 settles half-hourly and so carries no such coupling.

Note the interaction with §4.3: because $u(t)$ forces all discharge to zero in
a period where the battery charges, holding $d_2$ constant across the hour
means the battery cannot charge in one half hour and sell into Market 2 in the
other half of the same hour. That is the intended physical behaviour: a
commitment to deliver into Market 2 must be honoured for the full hour.

### 4.6 Cycle life

The brief defines one cycle as charging to the maximum storage volume and then
discharging all of it, and allows the energy to be accumulated in parts. The
equivalent full cycles used over the horizon are therefore the total energy
throughput divided by the storage volume, and that total is capped by the
battery's cycle life.

A cycle is only completed when the energy is discharged, so the count is taken
on the discharge side alone: charging without discharging consumes no cycle
life. 

Cycles are accumulated period by period, so the count is available at every $t$
for the degradation in §4.7:

$$
\begin{aligned}
n_{\text{cyc}}(t) &= n_{\text{cyc}}(t-1) + \frac{\Delta t \,\bigl(d_1(t) + d_2(t)\bigr)}{\overline{S}_{\max}} \qquad \forall t \in \mathcal{T} \\[6pt]
n_{\text{cyc}}(0) &= 0 \\[6pt]
n_{\text{cyc}}(T) &\leq \overline{L}
\end{aligned}
$$

$n_{\text{cyc}}(t)$ is non-decreasing, so capping the final value caps every
period. Throughput is measured at the storage side, matching the brief's
definition of a cycle in terms of stored volume: $d_1 + d_2$ is what leaves the
store. The nominal $\overline{S}_{\max}$ is the denominator rather than the
degraded $S_{\max}(t)$, which keeps the constraint linear.

### 4.7 Storage volume degradation

Each equivalent full cycle costs a fixed fraction $\rho$ of the storage volume,
applied to the cycles accumulated so far, so the usable volume shrinks as the
horizon progresses.

$$
S_{\max}(t) = \overline{S}_{\max}\,\bigl(1 - \rho \, n_{\text{cyc}}(t)\bigr) \qquad \forall t \in \mathcal{T}
$$

This is linear in $n_{\text{cyc}}(t)$, so introducing it keeps the problem a
MILP. At the cycle limit the cumulative loss is $\rho \overline{L} = 5\%$ of
the nominal volume.

$S_{\max}(t)$ is a convenience rather than a necessity: it appears only in
§4.1 and §4.4, where substituting the expression above turns each bound into a
constraint on $S(t)$ and $n_{\text{cyc}}(t)$ directly. An implementation may
drop the variable; the write-up keeps it because it names the quantity.

## 5. Assumptions and simplifications

The brief invites simplification over completeness. Choices made here:

- **Price taker.** Stated in the brief; prices are exogenous.
- **The battery starts empty.** $S(0) = 0$. The balance needs some initial
  state; the alternatives are to leave $S(0)$ free, or to impose a cyclic
  condition $S(T) = S(0)$ so the horizon neither starts nor ends with a
  windfall.
- **The rate limits are battery capabilities, not grid limits.** Attachment 1
  describes them as the power the battery can import from and export to the
  grid, which would put them on the grid side of the converter. They are read
  instead as limits on the battery's own charge and discharge power, so each
  bounds its variable directly. 
- **The cycle budget is the full 5,000 over a three-year horizon.** The price
  data covers three of the battery's ten calendar years, so spending the entire
  cycle life within it implies retiring the asset early. Pro-rating to
  $\tfrac{3}{10} \times 5000 = 1500$ cycles would be the alternative. Which is
  right depends on whether the exercise is "maximise profit over this data" or
  "value the asset over its life"; the former is what the brief asks for.
- **Capex and opex do not enter the objective.** £500,000 capex and £5,000/year
  fixed opex are fixed with respect to the dispatch decision, so they do not
  change the optimal schedule; they belong to a separate economic assessment of
  the asset.

### Data handling

Two artefacts of UK daylight saving are present in the price series and are
reported by `battery-case inputs` rather than silently repaired:

- Market 1 repeats two half hours at each spring clock change (2018-03-25,
  2019-03-31, 2020-03-29), so its timestamp index is not monotonic there.
  Neither market contains the extra repeated hour at the autumn changes.
- Market 2's Excel timestamps carry float rounding (`00:59:59.999`), rounded to
  the minute on load.

Because the hourly coupling in §4.5 is defined by grouping periods into hours,
the treatment of these periods needs stating before the model is built.

## 6. Solution approach

### Solver

HiGHS, through `pulp`. Both are already dependencies, and HiGHS reads the model
in process rather than through a file, which matters because the horizon is
solved as a sequence of many small programs rather than one large one.

### Why the horizon is decomposed

Posed whole, the program carries one binary $u(t)$ for each of the 52,608
periods. Solve time grows steeply, and erratically, with the window length: on
this data a day solves in about 0.04 s and two days in 0.2 s, but a week takes
around 3 s and a fortnight anywhere from 5 s to 17 s depending on which
fortnight it is. Extrapolating that to three years is not worth attempting, and
the unpredictability is itself a reason to prefer windows small enough to solve
reliably.

The horizon is therefore walked in windows. Each window solves
$\text{commit} + \text{lookahead}$ periods, keeps the decisions of the
committed part, and hands $S$ and $n_{\text{cyc}}$ at that point to the next
window as its opening state. One day committed with one day of lookahead is the
default. The lookahead is solved and then discarded; without it each day would
be decided as if the horizon ended at midnight, and the battery would always
end the day empty even when the next morning pays more than the evening did.

### What decomposition costs

Two couplings reach beyond a single window:

- **State of charge.** Carried exactly by the handover, so the only loss is of
  foresight past the lookahead, not of feasibility.
- **Cycle life (§4.6).** Global. Each window carries the cycles already spent
  and caps the cumulative count, so the budget can never be overspent — but a
  window cannot see what a later one would have done with a cycle, so a binding
  budget is simply consumed by the earliest days that can use it.

The second is handled by pricing the budget rather than splitting it. A charge
$\lambda$ per equivalent full cycle is added to the objective,

$$
\max \sum_{t \in \mathcal{T}} R(t) - \lambda \, n_{\text{cyc}}(T)
$$

which makes each window spend a cycle only on a spread worth at least
$\lambda$. The $\lambda$ wanted is the budget's shadow price: the largest
charge at which the horizon still spends its whole budget. Cycle use falls
monotonically in $\lambda$, so it is found by bisection, re-solving the horizon
at each step.

On this data, with the full 5,000-cycle budget of §5, the cap is never reached
and $\lambda = 0$: the round-trip loss of §4.2 rules out the narrow spreads
long before the cycle budget runs out, so the windows need no rationing and the
decomposition loses only the foresight past its lookahead. Unrationed dispatch
spends 3,443 cycles (§7), so under the pro-rated budget of 1,500 cycles the cap
*would* bind and $\lambda$ would become active; what it is worth there has not
been measured, since each bisection step re-solves the whole horizon.

### How much foresight is enough

One day of lookahead is sufficient on this data. Over June 2018:

| Committed | Lookahead | Profit | Cycles |
| --- | --- | --- | --- |
| 1 day | none | £4,589 | 78.4 |
| 1 day | 1 day | £4,621 | 79.2 |
| 1 day | 2 days | £4,621 | 79.2 |
| 7 days | 1 day | £4,621 | 79.2 |

Deciding each day blind to the next costs 0.7%, and nothing is gained past the
first day of lookahead: committing a whole week at a time reaches the same
profit as committing one day with one day in view. That is what one would
expect of a 4 MWh store that can fill in two hours — its decisions do not
reach far beyond the day they are taken in, and the cycle budget, which is the
one thing that would couple distant days, is not binding.

## 7. Results

Over 2018-01-01 to 2020-12-31, dispatched by the rolling windows of §6 with the
full cycle budget:

| Figure | Value |
| --- | --- |
| **Profit** | **£207,365** |
| Energy bought | 14,497 MWh at a mean £34.98/MWh |
| Energy delivered | 13,083 MWh at a mean £54.61/MWh |
| Equivalent full cycles | 3,443 of 5,000 |
| Storage volume at the end | 3.86 MWh, from 4.00 nominal |
| Periods charging / discharging / idle | 16,778 / 15,181 / 20,649 of 52,608 |
| Profit per cycle spent | £60.23 |

Reproduce with `uv run battery-case dispatch`, which writes the half-hourly
schedule every figure above is read off.

### Reading the result

**The markets are used as a pair, not interchangeably.** Market 2 is dearer
than Market 1 in 77.5% of periods, by £3.51/MWh on average, and the schedule
takes that: of the 14,497 MWh bought, 11,210 is bought in Market 1, and of the
13,083 MWh delivered, 11,174 goes into Market 2. Part of the profit is
arbitrage over time, part is the standing gap between the two markets, and the
hourly commitment of §4.5 is what the second part is paid for bearing.

**The cycle budget does not bind.** 3,443 cycles of the 5,000 available are
used, so no cycle is rationed and the shadow price of §6 is zero. Degradation
costs $\rho \, n_{\text{cyc}}(T) = 3.4\%$ of the storage volume by the end of
2020, leaving 3.86 of the nominal 4 MWh. Under the pro-rated budget of 1,500
cycles discussed in §5 the cap would bind, and the dispatch would be materially
different — fewer, wider spreads.

**The result improves as prices fall.** Year by year:

| Year | Profit | Mean Market 1 price | Mean Market 2 price | Cycles |
| --- | --- | --- | --- | --- |
| 2018 | £67,478 | £58.22/MWh | £61.72/MWh | 967 |
| 2019 | £63,991 | £41.84/MWh | £45.35/MWh | 1,166 |
| 2020 | £75,897 | £33.33/MWh | £36.84/MWh | 1,311 |

2020 is the most profitable year on the cheapest prices. The battery is paid
for the *spread*, not the level, and the spread widened as the level fell —
which is also why it trades more each year, 967 cycles in 2018 against 1,311 in
2020.

**Scale.** A perfect-foresight yardstick of one ideal 4 MWh cycle a day, bought
at each day's lowest price and sold at its highest, earns £178,254 over the same
horizon. The model earns £207,365 because it is not limited to one cycle a day:
it averages 3.1, taking narrower spreads as well as the daily best. That the
two are the same order of magnitude is the sanity check on the result.

**What capex and opex would do to it.** Excluded from the objective per §5, but
for context: £207,365 of trading profit over three years against £500,000 capex
and £5,000/year fixed opex leaves the asset £307,635 short of paying for itself
on this data, before any revenue stream other than wholesale arbitrage.

---

## Reading and rendering this document

It renders as-is on GitHub, which needs no toolchain. To render it locally:

```bash
make preview   # render to HTML and open in the browser
make html      # re-render after an edit, then refresh the page
make pdf       # export a PDF
```

`preview` and `html` need `pandoc`; `pdf` also needs `tectonic`. The HTML uses
MathJax, the same engine GitHub uses, so the local preview and the rendered
repository agree. The equations are written to the intersection of the two:
`$$` and `$` delimiters, `aligned` rather than `align`, and no cross-references.
