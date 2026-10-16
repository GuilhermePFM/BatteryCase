# What happens in a solve

*Why the horizon is decomposed, what one window does, and the evidence that a
day of foresight is enough.*

[← README](../README.md) · [data](data.md) · [architecture](architecture.md) ·
[cycle budget](cycle-budget.md) · [validation](validation.md)

---

## The pipeline

```mermaid
flowchart TD
    X1["attachment_1_battery_spec.xlsx"] --> L1["load_battery_spec"]
    X2["attachment_2_market_prices.xlsx"] --> L2["load_market_prices"]
    L1 --> S["BatterySpec<br/><i>spreadsheet units</i>"]
    L2 --> P["MarketPrices<br/><i>native resolutions</i>"]
    S --> PA["ModelParameters.from_spec<br/><i>§2 — units converted once</i>"]
    P --> G["build_grid<br/><i>§1, §5 — one half-hourly grid</i>"]
    PA --> R["RollingDispatcher.run_on_grid<br/><i>§6 — 1,096 windows</i>"]
    G --> R
    R --> SC["build_schedule<br/><i>§7 — one DataFrame</i>"]
    SC --> SU["summarise<br/><i>headline figures</i>"]
    SC --> OUT["data/results/dispatch_schedule.csv"]
```

## Why 1,096 programs and not one

`battery-case dispatch` over the full three years is **1,096 mixed-integer
programs**. The horizon carries a binary per period — the §4.3 exclusivity of
charging and discharging — and solve time grows steeply *and erratically* with
window length:

| Window | Solve time |
| --- | --- |
| 1 day (48 periods) | 0.04 s |
| 2 days | 0.2 s |
| 1 week | ~3 s |
| 1 fortnight | 5–17 s, depending which fortnight |

Extrapolating that to 52,608 periods is not a plan. So the horizon is walked.

## One window

```mermaid
flowchart LR
    subgraph W1["window 1 — one MILP, 96 periods"]
        direction LR
        C1["committed · 48p"] --- L1["lookahead · discarded"]
    end
    subgraph W2["window 2"]
        direction LR
        C2["committed · 48p"] --- L2["lookahead · discarded"]
    end
    subgraph W3["window 3"]
        direction LR
        C3["committed · 48p"] --- L3["lookahead · discarded"]
    end
    W1 -->|"S, n_cyc"| W2 -->|"S, n_cyc"| W3
```

Each window is solved with a day of foresight and committed for only half of
what it solved. The lookahead exists so the committed day is not decided as if
the world ended at midnight; it is then thrown away.

Two numbers cross each boundary, carried in a `BatteryState`: the **state of
charge** and the **cumulative cycle count**. The handover carries them exactly,
which is why the decomposition stays feasible — and why only the cycle
*budget*, which couples periods arbitrarily far apart, needed
[special handling](cycle-budget.md).

```mermaid
gantt
    title Rolling windows — solve 96 periods, keep 48, carry the state forward
    dateFormat YYYY-MM-DD
    axisFormat %d %b

    section Window 1
    committed (48p)       :done,    w1c, 2018-01-01, 1d
    lookahead, discarded  :active,  w1l, 2018-01-02, 1d

    section Window 2
    committed (48p)       :done,    w2c, 2018-01-02, 1d
    lookahead, discarded  :active,  w2l, 2018-01-03, 1d

    section Window 3
    committed (48p)       :done,    w3c, 2018-01-03, 1d
    lookahead, discarded  :active,  w3l, 2018-01-04, 1d
```

Both lengths are tunable from the CLI (`--commit-days`, `--lookahead-days`) and
both must be a whole number of hours, so a Market 2 commitment is never split
across a boundary.

## End to end

```mermaid
sequenceDiagram
    autonumber
    participant CLI as cli.py
    participant IO as data_io
    participant G as build_grid
    participant R as RollingDispatcher
    participant M as milp / HiGHS
    participant S as schedule

    CLI->>IO: load Attachment 1 + 2
    IO-->>CLI: BatterySpec, MarketPrices
    CLI->>G: build_grid(prices)
    G-->>CLI: 52,608 half-hourly periods,<br/>relabelled from Market 2, trimmed on whole hours
    CLI->>R: run_on_grid(grid, ModelParameters.from_spec(spec))
    loop 1,096 times — one per day
        R->>M: solve 96 periods (48 committed + 48 lookahead)
        M-->>R: WindowSolution
        R->>R: keep first 48, discard the rest,<br/>carry BatteryState (storage, cycles)
    end
    R->>S: build_schedule(committed slices)
    S-->>CLI: DataFrame + summarise()
    CLI->>CLI: write data/results/dispatch_schedule.csv
```

One HiGHS instance is reused across every window. The full three years takes a
few minutes, with a progress line on stderr.

## Implementation details of the rolling loop

- **It is linear by construction.** 1,096 MILPs of fixed size (96 periods, 96
  binaries) rather than one of 52,608 — cost grows linearly in the horizon,
  where a single program's does not. One `HiGHS` solver object is built per
  pass and reused across every window.
- **No warm starts.** Consecutive windows differ only in their prices and their
  opening state, so each solve rebuilds a model it has essentially seen before.
  This is the clearest remaining speed-up and it is not implemented.
- **The last window keeps what it has.** `min(commit_periods, len(window))`
  commits the tail when the horizon does not divide evenly, and the final
  window simply has no lookahead to discard.
- **Windows are whole hours by assertion.** `__post_init__` rejects anything
  else, because an hourly Market 2 pair of §4.5 split across a boundary would
  let the two halves be committed to different prices.
- **The handover is two floats.** `state_after(committed)` reads *S* and
  *n_cyc* at the last committed period — exactly the two quantities the next
  window's first-period constraints need.
- **S_max is substituted, not solved for.** §4.7 lets the degraded capacity be
  folded into the storage bound (`storage[t] + volume * rho * n_cyc[t] <=
  volume`), which keeps 52,608 variables out of the full program.

## Is one day of foresight enough?

On this data, yes — and it is checked rather than assumed. Over June 2018:

| Configuration | Profit | Against the 1d + 1d baseline |
| --- | --: | --- |
| commit 1 day, **no** lookahead | | −0.7% |
| commit 1 day, 1 day lookahead | £4,621 | baseline |
| commit 1 week, 1 day lookahead | £4,621 | identical, to the penny |

Deciding each day completely blind to the next costs 0.7%; committing a whole
week at a time earns *exactly* the same. A 4 MWh store that fills in two hours
simply does not have decisions that reach far beyond the day they are taken in
— the state of charge it can carry across midnight is worth at most two hours
of discharge.

The caveat is in [validation](validation.md#still-open): this is one month, and
a month where the cycle budget mattered would test it harder.
