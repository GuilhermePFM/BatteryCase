# Battery dispatch model

Formulation of the battery dispatch problem for the Aurora second-round
technical exercise: a 2 MW / 4 MWh battery trading across two wholesale
electricity markets over 2018–2020, as a price taker.

---

## 1. Problem statement

A battery buys energy when prices are low and sells when they are high. Two
wholesale markets are available, quoted in £/MWh and settled at different
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
| $\overline{S}_{\max}$ | 4 | MWh | maximum storage volume |

Parameter values are from Attachment 1.

### Decision variables

| Symbol | Domain | Unit | Meaning |
| --- | --- | --- | --- |
| $c_1(t)$ | $\geq 0$ | MW | charging power bought from Market 1 |
| $c_2(t)$ | $\geq 0$ | MW | charging power bought from Market 2 |
| $d_1(t)$ | $\geq 0$ | MW | discharging power sold into Market 1 |
| $d_2(t)$ | $\geq 0$ | MW | discharging power sold into Market 2 |
| $S(t)$ | $\geq 0$ | MWh | energy stored |
| $u(t)$ | binary | – | 1 when charging, 0 when discharging |

## 3. Objective

Maximise total profit over the horizon. Revenue in a period is the energy sold
into each market at that market's price, less the energy bought; the factor
$\Delta t = \tfrac{1}{2}$ converts power in MW to energy in MWh over the
half-hourly period.

$$
\max \sum_{t \in \mathcal{T}} R(t)
$$

where

$$
\begin{aligned}
R(t) &= \frac{p_1(t) \cdot d_1(t) + p_2(t) \cdot d_2(t) - p_1(t) \cdot c_1(t) - p_2(t) \cdot c_2(t)}{2} \\[4pt]
     &= \frac{p_1(t)\,\bigl(d_1(t) - c_1(t)\bigr) + p_2(t)\,\bigl(d_2(t) - c_2(t)\bigr)}{2}
\end{aligned}
$$

## 4. Constraints

### 4.1 Storage bounds

Stored energy stays between empty and the maximum storage volume.

$$
0 \leq S(t) \leq \overline{S}_{\max} \qquad \forall t \in \mathcal{T}
$$

### 4.2 Energy balance

Energy stored carries from one period to the next, increased by what was
charged and reduced by what was discharged in the preceding period.

$$
S(t) = S(t-1) + c_1(t-1) + c_2(t-1) - d_1(t-1) - d_2(t-1) \qquad \forall t \in \mathcal{T}
$$

### 4.3 Charge or discharge, not both

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

### 4.4 Capacity constraints

Charging is limited by the headroom remaining in the store, and discharging by
what the store holds.

$$
\begin{aligned}
c_1(t) + c_2(t) &\leq \overline{S}_{\max} - S(t-1) \\[4pt]
d_1(t) + d_2(t) &\leq \overline{S}_{\max}
\end{aligned}
$$

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
other half of the same hour. That is the intended physical behaviour — a
commitment to deliver into Market 2 must be honoured for the full hour — but it
does tighten the schedule relative to Market 1, which can be traded in either
direction in either half hour.

## 5. Assumptions and simplifications

The brief invites simplification over completeness. Choices made here:

- **Price taker.** Stated in the brief; prices are exogenous.
- **Round-trip efficiency is omitted.** Attachment 1 gives a 5% loss on charge
  and 5% on discharge; the energy balance above applies neither. The battery is
  therefore modelled as lossless, which overstates profit and narrows the price
  spread needed to make a cycle worthwhile.
- **Degradation and cycle life are out of scope.** $\overline{S}_{\max}$ is
  constant; the 0.001 %/cycle fade and the 5,000-cycle limit do not constrain
  the schedule.
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

## 6. Open points in the formulation

Raised against the formulation as written above, ordered by how much they
affect the result.

1. **Flows at the final period are never debited from storage.** The balance in
   §4.2 writes $S(t)$ in terms of the flows at $t-1$, so the variables at
   $t = T$ appear in the objective but in no balance constraint. The model can
   therefore discharge freely in the last period at no cost to the store,
   bounded only by $\overline{D}$. Either index the balance on the flows at $t$,
   or add a terminal constraint for $S(T+1)$.

2. **The energy balance is dimensionally inconsistent.** $S$ is in MWh while
   $c$ and $d$ are in MW. The objective applies $\Delta t = \tfrac{1}{2}$, but
   §4.2 and §4.4 do not, so one half-hour at 2 MW adds 2 MWh to the store
   rather than 1 MWh — effectively doubling the battery's throughput. The
   factor is needed wherever power enters an energy equation.

3. **$d_1(t) + d_2(t) \leq \overline{S}_{\max}$ is almost certainly meant to be
   $\leq S(t-1)$.** As written it bounds discharge by the size of the store
   rather than its contents, permitting a full discharge from an empty battery.
   In practice $S(t) \geq 0$ in §4.1 already enforces the correct bound through
   the balance, which makes both constraints in §4.4 redundant — harmless, and
   occasionally useful to the solver, but worth knowing they are not what is
   doing the work.

4. **The binary is load-bearing here, more than it would normally be.** With
   two markets priced differently in the same period and no round-trip loss,
   buying in the cheaper market and selling in the dearer one within a single
   period is pure profit, so without $u(t)$ the model would do it at every
   opportunity. Reinstating the efficiencies would suppress most of that, and
   the data contains negative prices, so it is worth checking whether the
   binaries can be relaxed — $|\mathcal{T}| = 52{,}608$ of them is the main
   driver of solve time.

## 7. Solution approach

<!-- TODO: solver choice, and whether the horizon is solved whole or decomposed
     (for example day by day with a linking state of charge). -->

## 8. Results

<!-- TODO: headline profit, and whatever supports it. -->

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
