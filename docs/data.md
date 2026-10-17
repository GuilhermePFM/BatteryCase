# The inputs

*The two spreadsheets, what they contain, and the artefact that shapes how the
model pairs them.*

[← README](../README.md) · [architecture](architecture.md) · [solve](solve.md) ·
[cycle budget](cycle-budget.md) · [validation](validation.md)

---

## Attachment 1: the battery

`data/raw/attachment_1_battery_spec.xlsx`

| | |
| --- | --- |
| Charge / discharge rate | 2 MW each way |
| Storage volume | 4 MWh (fills in two hours) |
| Charge loss | 5% |
| Discharge loss | 5% |
| Lifetime | 10 years / 5,000 cycles |
| Degradation | 0.001% of volume per equivalent full cycle |
| Capex | £500,000 |
| Fixed opex | £5,000 / year |

Capex and fixed opex appear nowhere in the dispatch objective: per §5 of the
formulation they do not depend on the decision. They belong to the investment
question rather than to the dispatch one.

`BatterySpec` holds these ten fields **in the spreadsheet's own units**, loss
fractions as fractions and degradation in percent, so that the loader can be
checked against the file line by line. Every unit conversion happens once, in
`ModelParameters.from_spec`.

## Attachment 2: the prices

`data/raw/attachment_2_market_prices.xlsx`, £/MWh over 2018-01-01 to 2020-12-31.

| Market | Resolution | Rows | Note |
| --- | --- | --: | --- |
| Market 1 | half-hourly | 52,608 | the settlement grid the model runs on |
| Market 2 | hourly | 26,304 | written on the half-hourly grid with blank rows on the half hours |

The blank half-hour rows are dropped on load, so each series keeps its own
native resolution. The hourly price is repeated across its two half hours later,
in `build_grid`, where it is a modelling step rather than a loading one.

## The quirks, surfaced and deliberately not repaired

`uv run battery-case inputs` prints a quality report. `price_quality_report`
counts duplicate timestamps, irregular steps and monotonicity per market, and
*returns* them. It is not a cleaner: how to treat these periods is a modelling
decision, so it is made visibly in `modelling/grid.py` rather than invisibly on
load.

**1. Market 1 mislabels the spring clock change.** At 2018-03-25, 2019-03-31
and 2020-03-29 the sheet labels the 01:00–02:00 hour as 02:00, repeating two
half hours, so the index is not monotonic there. Neither market repeats the
extra hour at the autumn changes.

```
Market 1 labels    …  00:30   01:00   01:30   02:00   02:00   02:30  …
Market 2 labels    …          01:00           02:00           02:30  …   ← canonical
                                                   ↑ the duplicate label
```

`build_grid` takes **Market 2's labels as canonical**, which repairs the
artefact without moving any price off the period it was quoted for.

**2. Excel float timestamps.** Market 2's timestamps are stored as floats and
some land on `00:59:59.999`. The loader rounds them to the minute.

**3. Row order carries meaning.** It is the order the settlement periods occur
in, and the grid relies on it, so the loader preserves it.

## Why pairing is positional

Because of quirk 1, the two series cannot be joined on their labels. They are
paired by **position**: every day holds exactly 48 and 24 rows, so position is
trustworthy where the Market 1 labels are not.

For the same reason `MarketPrices.between()` filters with a boolean mask rather
than `.loc` slicing. Label slicing on a non-monotonic index would raise.

Four tests cover this ground (`test_data_io.py`), plus the relabelling itself in
`test_grid.py`. See [validation](validation.md).

## Missing rows fail loudly

`load_battery_spec` reads Attachment 1 through `_SPEC_FIELDS`, an explicit
*spreadsheet label → field name* map, and raises listing **every** missing row
rather than producing a spec with a silent default. A renamed row in the source
file then fails outright instead of yielding a plausible wrong answer.
