# Battery dispatch model

Aurora second-round technical exercise: a Python package that models a battery
charging and discharging across two wholesale electricity markets to maximise
profit.

> **Status:** repository scaffolding and data loading only. The dispatch
> methodology is not implemented yet — see [Where the model goes](#where-the-model-goes).

## Setup

The project uses [uv](https://docs.astral.sh/uv/). Python 3.12 is pinned in
`.python-version` and installed by uv if missing.

```bash
uv sync --all-groups   # create .venv and install runtime + dev dependencies
```

## Running

```bash
uv run battery-case inputs    # load and summarise both spreadsheets
```

## Development

```bash
uv run ruff format .      # format
uv run ruff check . --fix # lint
uv run mypy               # type check (strict)
uv run pytest             # tests
uv run jupyter lab        # notebooks
```

## Layout

```
data/raw/      the two spreadsheets supplied with the exercise
data/results/  model outputs (git-ignored)
docs/brief/    the exercise brief, as supplied
docs/model/    model.md — the formulation (renders on GitHub)
notebooks/     exploratory analysis
src/battery_case/
  paths.py     where the inputs and outputs live
  battery.py   BatterySpec — the asset parameters, in the units given
  data.py      spreadsheet loaders and a data quality report
  dispatch.py  the seam the dispatch model plugs into
  cli.py       the `battery-case` command
tests/
```

## The inputs

**Attachment 1 — battery** (`data/raw/attachment_1_battery_spec.xlsx`): 2 MW
charge and discharge, 4 MWh storage, 5% loss on charge and 5% on discharge,
10-year / 5,000-cycle life, 0.001%/cycle storage degradation, £500,000 capex,
£5,000/year fixed opex.

**Attachment 2 — prices** (`data/raw/attachment_2_market_prices.xlsx`): £/MWh
over 2018-01-01 to 2020-12-31. Market 1 is half-hourly (52,608 periods),
Market 2 hourly (26,304 periods, written on the half-hourly grid with blank
rows on the half hours).

### Known data quirks

Surfaced by `uv run battery-case inputs`, and deliberately **not** repaired by
the loader — how to treat these periods is a modelling decision:

- Market 1 repeats two half hours at each spring clock change
  (2018-03-25, 2019-03-31, 2020-03-29), so its index is not monotonic there.
  Neither market repeats the extra hour at the autumn clock changes.
- Market 2's Excel timestamps carry float rounding (`00:59:59.999`); the loader
  rounds them to the minute.

## Where the model goes

The formulation is written up in [`docs/model/model.md`](docs/model/model.md).
`src/battery_case/dispatch.py` defines the `Dispatcher` protocol — prices in,
schedule out — and nothing else. The modelling choices still open:

- how the two markets' different resolutions are reconciled, given capacity
  committed to a market is committed for that market's whole interval;
- the decision logic itself (LP/MILP optimisation or a simpler heuristic);
  `pulp` and `highspy` are already dependencies if an optimiser is wanted;
- whether degradation, cycle life and the capex/opex economics are in scope.

## Approach

_One paragraph, to be written once the model is built (required deliverable)._
