# Battery dispatch model

**Aurora second-round technical exercise.** A 2 MW / 4 MWh battery, two
wholesale electricity markets at different settlement resolutions, and three
years of half-hourly prices. What should the battery do, and what is that worth?

**£207,365** of trading profit over 2018–2020, using **3,443 of the battery's
5,000 cycles**, from a mixed-integer linear program solved as 1,096 rolling
daily windows.

| | |
| --- | --- |
| **Profit, 2018–2020** | £207,365 |
| **Cycles used** | 3,443 of 5,000 |
| **Periods dispatched** | 52,608 half hours |
| **MILPs solved per run** | 1,096 |
| **Tests** | 64, green in ~10 s |
| **Source** | 1,833 lines under `src/` |

## The problem in one picture

The battery buys and sells in two markets. Market 1 settles every half hour;
Market 2 settles hourly, so anything committed to it is committed for the whole
hour. Energy is lost on the way in and on the way out, and every MWh pushed
through wears the asset out a little.

```mermaid
flowchart LR
    M1["<b>Market 1</b><br/>half-hourly<br/>52,608 prices"]
    M2["<b>Market 2</b><br/>hourly<br/>26,304 prices"]
    B["<b>Battery</b><br/>2 MW in / 2 MW out<br/>4 MWh store"]

    M1 -- "buy (−5% on charge)" --> B
    M2 -- "buy (−5% on charge)" --> B
    B -- "sell (−5% on discharge)" --> M1
    B -- "sell (−5% on discharge)" --> M2

    B -.-> D["<b>Wear</b><br/>0.001% volume lost<br/>per equivalent full cycle<br/>5,000-cycle life"]
```

Three consequences shape the rest:

- **A round trip keeps only 90.25%** of what it buys (0.95 × 0.95), so a spread
  has to beat about 11% before a trade is worth making.
- **Charging and discharging must be mutually exclusive.** The two markets
  diverge, so without a binary forbidding it the battery would buy in one and
  sell into the other in the same instant, wheeling energy it never stores.
- **Market 2's decisions are held flat across each hour**, imposed on the
  decision variables rather than on the prices, because that is what committing
  capacity to an hourly product means.

The result is a MILP on a common half-hourly grid, solved a day at a time with a
day of foresight. 52,608 periods each carrying a binary is not one tractable
program.

## Running it

The project uses [uv](https://docs.astral.sh/uv/). Python 3.12 is pinned in
`.python-version` and installed by uv if missing.

```bash
uv sync --all-groups            # create .venv, install runtime + dev deps

uv run battery-case inputs      # load both spreadsheets, print spec + data quality
uv run battery-case dispatch    # solve all three years (a few minutes)
```

`dispatch` writes the half-hourly schedule to `data/results/` and prints the
headline figures. Restrict it for a quick look:

```bash
uv run battery-case dispatch --start 2018-01-01 --end 2018-01-31
```

| Flag | Default | What it changes |
| --- | --- | --- |
| `--start` / `--end` | all data | Horizon, trimmed on whole hours |
| `--commit-days` | `1` | How much of each solved window is kept |
| `--lookahead-days` | `1` | Foresight beyond the committed part, then discarded |
| `--cycle-price` | `0.0` | £ charged per equivalent full cycle used |
| `--cycle-pricer` | none | Search for that charge instead, by `bisection` or `cutting-plane` (§6) |
| `--out` | `data/results/dispatch_schedule.csv` | `.csv` or `.parquet` |

The cycle budget only needs a charge when it binds, and on the full 5,000-cycle
budget it does not, so `--cycle-pricer` costs one pass and returns zero. It
matters under the pro-rated budget of §5. Compare the two methods on one
instance with:

```bash
uv run python scripts/compare_pricers.py 30    # one instance, against an exact solve
uv run python scripts/sweep_pricers.py         # 1 to 90 days, both methods side by side
```

Development:

```bash
uv run pytest             # 64 tests, ~10 s
uv run mypy               # strict
uv run ruff check . --fix
uv run ruff format .
make preview              # render docs/model/model.md to HTML and open it
```

## Where to read what

```mermaid
flowchart TD
    R["<b>README</b><br/>the problem, the answer, how to run it"]
    M["<b>docs/model/model.md</b><br/>the formulation · the maths, §1–§7"]
    D["<b>docs/data.md</b><br/>the two attachments and their quirks"]
    A["<b>docs/architecture.md</b><br/>the packages, every file, the decision inside it"]
    S["<b>docs/solve.md</b><br/>what happens in a solve · the rolling horizon"]
    C["<b>docs/cycle-budget.md</b><br/>the one constraint decomposition can get wrong<br/>and the λ that fixes it"]
    X["<b>docs/model/cycle-price-experiments.md</b><br/>bisection vs cutting planes, measured<br/>against an exact solve"]
    ST["<b>docs/model/model-stochastic.md</b><br/>the same model with stochastic prices<br/>formulation only"]
    V["<b>docs/validation.md</b><br/>what is checked, what was found, what is open"]

    R --> M
    R --> D --> A --> S --> C --> V
    M --> X
    C --> X
    M --> ST
```

| Document | Read it for |
| --- | --- |
| [`docs/model/model.md`](docs/model/model.md) | The formulation: objective, constraints, assumptions, numbered §1–§7. Every module cites it. |
| [`docs/model/model-stochastic.md`](docs/model/model-stochastic.md) | The multistage stochastic extension: scenario tree, non-anticipativity, the cycle cap under uncertainty, mean-CVaR. Formulation only, nothing implemented. |
| [`docs/data.md`](docs/data.md) | What the two spreadsheets contain, the clock-change artefacts, and why the loader reports rather than repairs. |
| [`docs/architecture.md`](docs/architecture.md) | How the code is filed, the dependency rule, every class with the reason it exists, why the constraints are separate blocks, and how two pricing algorithms share one seam. |
| [`docs/solve.md`](docs/solve.md) | Why the horizon is decomposed, what one window does, and the evidence that a day of foresight suffices. |
| [`docs/cycle-budget.md`](docs/cycle-budget.md) | The global cycle cap, the bug decomposing it exposed, pricing cycles instead of splitting them, and how λ is found by bisection. |
| [`docs/model/cycle-price-experiments.md`](docs/model/cycle-price-experiments.md) | Why a capped pass has no usable gradient, and both pricing methods measured against exactly solved instances: passes, λ, profit and the dual bound. |
| [`docs/model/tractability.md`](docs/model/tractability.md) | Solve time against window length, and the whole horizon as one MILP: the measurements behind decomposing it. |
| [`docs/pricer-build-report.md`](docs/pricer-build-report.md) | What was built for the two pricing methods, the three deviations from the proposal, the one item not built and why, and the evidence each claim was checked against. |
| [`docs/validation.md`](docs/validation.md) | The 64 tests, what checking found that thinking had not, and the questions still open. |

## Layout

```
src/battery_case/   the package, described in docs/architecture.md
tests/              64 tests, described in docs/validation.md
data/raw/           the two spreadsheets supplied with the exercise
data/results/       model outputs
docs/brief/         the exercise brief, as supplied
docs/model/         the formulation, plus the solver experiments behind it
notebooks/          exploratory analysis
Makefile            render targets for the model document
```

---

Figures come from `data/results/dispatch_schedule.csv`, reproduced identically
across two independent full-horizon runs.
