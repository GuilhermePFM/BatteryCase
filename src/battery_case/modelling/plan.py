"""The dispatch plan and the figures read off it.

The plan is the model's output: one row per half-hourly period, holding the
decisions of §2 and the revenue of §3. Every quantity a result quotes is
recomputed from these columns, so the write-up and the code cannot drift.

The revenue columns are *net* of what was bought in that market, so a market
the battery mostly buys in carries a negative total over the horizon while the
profit across both is positive. Capex and fixed opex appear nowhere: per §5
they do not depend on the dispatch decision.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from battery_case.modelling.parameters import ModelParameters
from battery_case.modelling.periods import SettlementPeriods

#: Power below this is the solver's zero, not a decision to trade (MW).
#:
#: 10 W, an order of magnitude above the solver's feasibility tolerance. A MILP
#: is solved to a tolerance, not exactly, so a variable the solver means to hold
#: at zero can come back at 1e-6: left in, such a value shows up as the battery
#: charging and discharging in the same period, which §4.3 forbids.
_TOLERANCE = 1e-5

#: Columns of a dispatch plan, in order.
COLUMNS = (
    "price_1",
    "price_2",
    "charge_1_mw",
    "charge_2_mw",
    "discharge_1_mw",
    "discharge_2_mw",
    "storage_mwh",
    "effective_volume_mwh",
    "cycles",
    "net_revenue_1_gbp",
    "net_revenue_2_gbp",
    "net_revenue_gbp",
)


def build_plan(
    settlement: SettlementPeriods,
    params: ModelParameters,
    *,
    charge_1_mw: np.ndarray,
    charge_2_mw: np.ndarray,
    discharge_1_mw: np.ndarray,
    discharge_2_mw: np.ndarray,
    storage_mwh: np.ndarray,
    cycles: np.ndarray,
) -> pd.DataFrame:
    """Assemble the plan frame from the solved decision arrays."""
    charge_1_mw = _clean(charge_1_mw)
    charge_2_mw = _clean(charge_2_mw)
    discharge_1_mw = _clean(discharge_1_mw)
    discharge_2_mw = _clean(discharge_2_mw)
    storage_mwh = _clean(storage_mwh)
    delivered = 1.0 - params.discharge_loss
    revenue_1 = params.dt * settlement.price_1 * (delivered * discharge_1_mw - charge_1_mw)
    revenue_2 = params.dt * settlement.price_2 * (delivered * discharge_2_mw - charge_2_mw)

    frame = pd.DataFrame(
        {
            "price_1": settlement.price_1,
            "price_2": settlement.price_2,
            "charge_1_mw": charge_1_mw,
            "charge_2_mw": charge_2_mw,
            "discharge_1_mw": discharge_1_mw,
            "discharge_2_mw": discharge_2_mw,
            "storage_mwh": storage_mwh,
            "effective_volume_mwh": effective_volume(params, cycles),
            "cycles": cycles,
            "net_revenue_1_gbp": revenue_1,
            "net_revenue_2_gbp": revenue_2,
            "net_revenue_gbp": revenue_1 + revenue_2,
        },
        index=settlement.timestamps,
    )
    return frame[list(COLUMNS)]


def _clean(values: np.ndarray) -> np.ndarray:
    """Round the solver's zeros to zero, dropping negative-zero noise."""
    return np.where(np.abs(values) < _TOLERANCE, 0.0, values)


def effective_volume(params: ModelParameters, cycles: np.ndarray) -> np.ndarray:
    """``S_max(t)`` of §4.7, the usable volume after degradation."""
    return params.nominal_volume_mwh * (1.0 - params.degradation_per_cycle * cycles)


def summarise(plan: pd.DataFrame, params: ModelParameters) -> pd.Series:
    """Headline figures for a plan (§7).

    Profit is the objective of §3 summed over the horizon. Capex and fixed opex
    are excluded, per §5: they do not depend on the dispatch decision.

    ``income_gbp`` and ``cost_gbp`` split that profit by direction rather than
    by market: income is what the delivered energy sold for, net of the
    discharge loss, and cost is what the imported energy was bought for at the
    meter, so it includes the share the charging loss never puts in the store.

    The two closing figures are different quantities and are easy to confuse.
    ``final_storage_mwh`` is the energy still in the battery when the horizon
    ends — normally zero, since unsold energy earns nothing, and positive only
    where the battery was paid to take it. ``final_usable_volume_mwh`` is
    ``S_max(T)`` of §4.7, the capacity the store has left after degradation,
    which falls from the nominal volume as cycles are spent.
    """
    charged = plan["charge_1_mw"] + plan["charge_2_mw"]
    discharged = plan["discharge_1_mw"] + plan["discharge_2_mw"]
    delivered = 1.0 - params.discharge_loss

    bought_mwh = float(params.dt * charged.sum())
    delivered_mwh = float(params.dt * delivered * discharged.sum())
    cost_gbp = float(
        params.dt
        * (plan["price_1"] * plan["charge_1_mw"] + plan["price_2"] * plan["charge_2_mw"]).sum()
    )
    income_gbp = float(
        params.dt
        * delivered
        * (
            plan["price_1"] * plan["discharge_1_mw"] + plan["price_2"] * plan["discharge_2_mw"]
        ).sum()
    )

    return pd.Series(
        {
            "profit_gbp": float(plan["net_revenue_gbp"].sum()),
            "net_revenue_market_1_gbp": float(plan["net_revenue_1_gbp"].sum()),
            "net_revenue_market_2_gbp": float(plan["net_revenue_2_gbp"].sum()),
            "income_gbp": income_gbp,
            "cost_gbp": cost_gbp,
            "energy_bought_mwh": bought_mwh,
            "energy_delivered_mwh": delivered_mwh,
            "mean_buy_price_gbp_per_mwh": _per_mwh(cost_gbp, bought_mwh),
            "mean_sell_price_gbp_per_mwh": _per_mwh(income_gbp, delivered_mwh),
            "cycles_used": float(plan["cycles"].iloc[-1]),
            "cycle_budget": params.cycle_budget,
            "final_storage_mwh": float(plan["storage_mwh"].iloc[-1]),
            "final_usable_volume_mwh": float(plan["effective_volume_mwh"].iloc[-1]),
            "periods": len(plan),
            "periods_charging": int((charged > _TOLERANCE).sum()),
            "periods_discharging": int((discharged > _TOLERANCE).sum()),
        }
    )


def _per_mwh(total_gbp: float, energy_mwh: float) -> float:
    """Volume-weighted £/MWh, or NaN when nothing was traded."""
    return total_gbp / energy_mwh if energy_mwh > _TOLERANCE else float("nan")
