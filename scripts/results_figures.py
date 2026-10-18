"""Every figure [`results.md`](../docs/model/results.md) quotes, read off a saved plan.

    uv run python scripts/results_figures.py [plan.csv]

The headline table of §7 is printed by ``battery-case dispatch`` itself; the
rest of that document — the market split, the year-by-year progression, the
perfect-foresight yardstick, and what capex would do to the answer — is prose
around numbers nothing re-derived. This script re-derives them, from
``data/results/dispatch_plan.csv`` as written by a full-horizon run, so the
document and the plan cannot drift apart unnoticed.

Nothing here solves anything: the plan is the model's output and every figure
is an arithmetic reading of it, which is why this is seconds rather than
minutes.
"""

from __future__ import annotations

import sys

import pandas as pd

from battery_case.data_io.loaders import load_battery_spec
from battery_case.data_io.paths import RESULTS_DIR
from battery_case.modelling.parameters import ModelParameters
from battery_case.modelling.plan import summarise

#: Volume of the one ideal daily cycle the yardstick of §7 trades (MWh).
#:
#: The nominal volume, undegraded: the yardstick is a bound sketched by hand,
#: not a dispatch, so it spends no wear and loses no capacity.
YARDSTICK_VOLUME_MWH = 4.0


def yardstick_profit(plan: pd.DataFrame, params: ModelParameters) -> float:
    """One perfect 4 MWh cycle a day: buy at the day's floor, sell at its ceiling.

    The floor and the ceiling are taken over *both* markets, since a trader
    with perfect foresight would use whichever market is cheaper to buy in and
    whichever is dearer to sell into. Losses are charged the way §4.2 charges
    them: filling the store costs ``V / (1 - charge loss)`` at the meter, and
    emptying it delivers ``V (1 - discharge loss)`` to the market.

    It ignores the rate limits of §4.3, the hourly commitment of §4.5 and the
    cycle budget of §4.6, so it is not a bound on the model — it is the
    order-of-magnitude check that the model's answer is the right size.
    """
    daily = plan.groupby(plan.index.normalize())
    floor = daily[["price_1", "price_2"]].min().min(axis=1)
    ceiling = daily[["price_1", "price_2"]].max().max(axis=1)

    bought_mwh = YARDSTICK_VOLUME_MWH / (1.0 - params.charge_loss)
    delivered_mwh = YARDSTICK_VOLUME_MWH * (1.0 - params.discharge_loss)
    return float((delivered_mwh * ceiling - bought_mwh * floor).sum())


def by_year(plan: pd.DataFrame) -> pd.DataFrame:
    """Profit, the two mean prices, and cycles spent, one row per calendar year.

    Cycles are differenced because the plan's ``cycles`` column is cumulative
    over the horizon: the year's own spend is what the table reads.
    """
    years = plan.groupby(plan.index.year)
    cumulative = years["cycles"].last()

    return pd.DataFrame(
        {
            "profit_gbp": years["net_revenue_gbp"].sum(),
            "mean_price_1_gbp_per_mwh": years["price_1"].mean(),
            "mean_price_2_gbp_per_mwh": years["price_2"].mean(),
            "cycles": cumulative.diff().fillna(cumulative.iloc[0]),
        }
    )


def _row(label: str, value: str, unit: str = "") -> None:
    """One label/value line, on the same right edge the CLI's blocks use."""
    print(f"  {label:<34}{value:>20}" + (f"  {unit}" if unit else ""))


plan_path = sys.argv[1] if len(sys.argv) > 1 else RESULTS_DIR / "dispatch_plan.csv"
spec = load_battery_spec()
params = ModelParameters.from_spec(spec)

try:
    plan = pd.read_csv(plan_path, index_col=0, parse_dates=True)
except FileNotFoundError:
    raise SystemExit(
        f"no plan at {plan_path}\nsolve one first:  uv run battery-case dispatch"
    ) from None

figures = summarise(plan, params)
charged = plan["charge_1_mw"] + plan["charge_2_mw"]
discharged = plan["discharge_1_mw"] + plan["discharge_2_mw"]
delivered = 1.0 - params.discharge_loss
idle = int(figures["periods"] - figures["periods_charging"] - figures["periods_discharging"])

print(f"plan: {plan_path}")
print(f"{plan.index[0]:%Y-%m-%d} to {plan.index[-1]:%Y-%m-%d}, {len(plan):,} periods\n")

print("Headline (results.md, the table)")
_row("profit", f"{figures['profit_gbp']:,.2f}", "GBP")
_row(
    "energy bought",
    f"{figures['energy_bought_mwh']:,.0f} at {figures['mean_buy_price_gbp_per_mwh']:,.2f}",
    "MWh at GBP/MWh",
)
_row(
    "energy delivered",
    f"{figures['energy_delivered_mwh']:,.0f} at {figures['mean_sell_price_gbp_per_mwh']:,.2f}",
    "MWh at GBP/MWh",
)
_row(
    "equivalent full cycles",
    f"{figures['cycles_used']:,.0f} of {figures['cycle_budget']:,.0f}",
)
_row(
    "storage volume at the end",
    f"{figures['final_usable_volume_mwh']:,.2f} of {params.nominal_volume_mwh:,.2f}",
    "MWh",
)
_row(
    "charging / discharging / idle",
    f"{int(figures['periods_charging']):,} / {int(figures['periods_discharging']):,} / {idle:,}",
    f"of {int(figures['periods']):,}",
)
_row("profit per cycle spent", f"{figures['profit_gbp'] / figures['cycles_used']:,.2f}", "GBP")

print("\nThe markets as a pair")
_row("periods market 2 is dearer", f"{(plan['price_2'] > plan['price_1']).mean():.1%}")
_row("mean market 2 less market 1", f"{(plan['price_2'] - plan['price_1']).mean():,.2f}", "GBP/MWh")
_row(
    "bought in market 1 / market 2",
    f"{params.dt * plan['charge_1_mw'].sum():,.0f} / {params.dt * plan['charge_2_mw'].sum():,.0f}",
    "MWh",
)
_row(
    "delivered into market 1 / 2",
    f"{params.dt * delivered * plan['discharge_1_mw'].sum():,.0f} / "
    f"{params.dt * delivered * plan['discharge_2_mw'].sum():,.0f}",
    "MWh",
)
_row(
    "degradation, rho * cycles",
    f"{params.degradation_per_cycle * figures['cycles_used']:.2%}",
    "of volume",
)

print("\nYear by year")
table = by_year(plan)
print(f"  {'year':<6}{'profit':>14}{'mean market 1':>16}{'mean market 2':>16}{'cycles':>10}")
for year, figures_for_year in table.iterrows():
    print(
        f"  {year:<6}{figures_for_year['profit_gbp']:>14,.0f}"
        f"{figures_for_year['mean_price_1_gbp_per_mwh']:>16,.2f}"
        f"{figures_for_year['mean_price_2_gbp_per_mwh']:>16,.2f}"
        f"{figures_for_year['cycles']:>10,.0f}"
    )

print("\nScale, and the costs left out of the objective (§5)")
yardstick = yardstick_profit(plan, params)
_row("one ideal 4 MWh cycle a day", f"{yardstick:,.0f}", "GBP")
_row("the model, against that", f"{figures['profit_gbp'] / yardstick:.2f}", "times")
_row("cycles a day, mean", f"{figures['cycles_used'] / (len(plan) / 48):.1f}")
years_of_data = len(plan) / (48 * 365.25)
lifetime_cost = spec.capex_gbp + spec.fixed_opex_gbp_per_year * years_of_data
_row(
    "capex + opex over the horizon",
    f"{lifetime_cost:,.0f}",
    f"GBP ({years_of_data:.1f} years)",
)
_row("profit minus that", f"{figures['profit_gbp'] - lifetime_cost:,.0f}", "GBP")
