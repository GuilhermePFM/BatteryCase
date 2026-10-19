# Results: 2018–2020 dispatched

*What the formulation of [`model.md`](model.md) earns on the three years of price
data, and how to read it.*

[← README](../../README.md) · [model](model.md) · [cycle budget](../cycle-budget.md) ·
[architecture](../architecture.md) · [solve](../solve.md) · [validation](../validation.md)

---

Section numbers throughout refer to the write-up, [`model.md`](model.md).

Over 2018-01-01 to 2020-12-31, dispatched by the rolling windows of §6 with the full
cycle budget:

| Figure | Value |
| --- | --- |
| **Profit** | **£207,365** |
| Energy bought | 14,495 MWh at a mean £34.98/MWh |
| Energy delivered | 13,082 MWh at a mean £54.61/MWh |
| Equivalent full cycles | 3,443 of 5,000 |
| Storage volume at the end | 3.86 MWh, from 4.00 nominal |
| Periods charging / discharging / idle | 16,774 / 15,179 / 20,655 of 52,608 |
| Profit per cycle spent | £60.23 |

Reproduce with `uv run battery-case dispatch`, which writes the half-hourly
plan every figure above is read off; the figures in the reading below are
re-derived from that plan by
[`scripts/results_figures.py`](../../scripts/results_figures.py), and both
stages run together as `make results`.

### Reading the result

**The markets are used as a pair, not interchangeably.** Market 2 is dearer
than Market 1 in 77.5% of periods, by £3.51/MWh on average, and the plan
takes that: of the 14,495 MWh bought, 11,208 is bought in Market 1, and of the
13,082 MWh delivered, 11,171 goes into Market 2. Part of the profit is
arbitrage over time, part is the standing gap between the two markets, and the
hourly commitment of §4.5 is what the second part is paid for bearing.

**The cycle budget does not bind.** 3,443 cycles of the 5,000 available are
used, so no cycle is rationed and the shadow price of §6 is zero. Degradation
costs $\rho \, n_{\text{cyc}}(T) = 3.4\%$ of the storage volume by the end of
2020, leaving 3.86 of the nominal 4 MWh. Under the pro-rated budget of 1,500
cycles discussed in §5 the cap would bind, and the dispatch would be
materially different: fewer, wider spreads.

**The result improves as prices fall.** Year by year:

| Year | Profit | Mean Market 1 price | Mean Market 2 price | Cycles |
| --- | --- | --- | --- | --- |
| 2018 | £67,478 | £58.22/MWh | £61.72/MWh | 967 |
| 2019 | £63,991 | £41.84/MWh | £45.35/MWh | 1,165 |
| 2020 | £75,897 | £33.33/MWh | £36.84/MWh | 1,310 |

2020 is the most profitable year on the cheapest prices. The battery is paid
for the *spread* rather than the level, and the spread widened as the level
fell, which is also why it trades more each year: 967 cycles in 2018 against
1,310 in 2020.

**Scale.** A perfect-foresight yardstick of one ideal 4 MWh cycle a day, bought
at each day's lowest price and sold at its highest, earns £178,254 over the same
horizon. The model earns £207,365 because it is not limited to one cycle a day:
it averages 3.1, taking narrower spreads as well as the daily best. That the
two are the same order of magnitude is the sanity check on the result.

**What capex and opex would do to it.** Excluded from the objective per §5, but
for context: £207,365 of trading profit over three years against £500,000 capex
and £5,000/year fixed opex leaves the asset £307,638 short of paying for itself
on this data, before any revenue stream other than wholesale arbitrage.

