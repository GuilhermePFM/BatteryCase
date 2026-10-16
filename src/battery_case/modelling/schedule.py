"""The dispatch schedule and the figures read off it.

The schedule is the model's output: one row per half-hourly period, holding the
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

from battery_case.modelling.grid import DispatchGrid
from battery_case.modelling.parameters import ModelParameters

#: Power below this is the solver's zero, not a decision to trade (MW).
#:
#: 10 W, an order of magnitude above the solver's feasibility tolerance. A MILP
#: is solved to a tolerance, not exactly, so a variable the solver means to hold
#: at zero can come back at 1e-6: left in, such a value shows up as the battery
#: charging and discharging in the same period, which §4.3 forbids.
_TOLERANCE = 1e-5

#: Columns of a dispatch schedule, in order.
COLUMNS = (
    "price_1",
    "price_2",
    "charge_1_mw",
    "charge_2_mw",
    "discharge_1_mw",
    "discharge_2_mw",
    "storage_mwh",
    "storage_max_mwh",
    "cycles",
    "revenue_1_gbp",
    "revenue_2_gbp",
    "revenue_gbp",
)


def build_schedule(
    grid: DispatchGrid,
    params: ModelParameters,
    *,
    charge_1_mw: np.ndarray,
    charge_2_mw: np.ndarray,
    discharge_1_mw: np.ndarray,
    discharge_2_mw: np.ndarray,
    storage_mwh: np.ndarray,
    cycles: np.ndarray,
) -> pd.DataFrame:
    """Assemble the schedule frame from the solved decision arrays."""
    charge_1_mw = _clean(charge_1_mw)
    charge_2_mw = _clean(charge_2_mw)
    discharge_1_mw = _clean(discharge_1_mw)
    discharge_2_mw = _clean(discharge_2_mw)
    storage_mwh = _clean(storage_mwh)
    delivered = 1.0 - params.discharge_loss
    revenue_1 = params.dt * grid.price_1 * (delivered * discharge_1_mw - charge_1_mw)
    revenue_2 = params.dt * grid.price_2 * (delivered * discharge_2_mw - charge_2_mw)

    frame = pd.DataFrame(
        {
            "price_1": grid.price_1,
            "price_2": grid.price_2,
            "charge_1_mw": charge_1_mw,
            "charge_2_mw": charge_2_mw,
            "discharge_1_mw": discharge_1_mw,
            "discharge_2_mw": discharge_2_mw,
            "storage_mwh": storage_mwh,
            "storage_max_mwh": effective_volume(params, cycles),
            "cycles": cycles,
            "revenue_1_gbp": revenue_1,
            "revenue_2_gbp": revenue_2,
            "revenue_gbp": revenue_1 + revenue_2,
        },
        index=grid.timestamps,
    )
    return frame[list(COLUMNS)]


def _clean(values: np.ndarray) -> np.ndarray:
    """Round the solver's zeros to zero, dropping negative-zero noise."""
    return np.where(np.abs(values) < _TOLERANCE, 0.0, values)


def effective_volume(params: ModelParameters, cycles: np.ndarray) -> np.ndarray:
    """``S_max(t)`` of §4.7, the usable volume after degradation."""
    return params.nominal_volume_mwh * (1.0 - params.degradation_per_cycle * cycles)


def summarise(schedule: pd.DataFrame, params: ModelParameters) -> pd.Series:
    """Headline figures for a schedule (§7).

    Profit is the objective of §3 summed over the horizon. Capex and fixed opex
    are excluded, per §5: they do not depend on the dispatch decision.
    """
    charged = schedule["charge_1_mw"] + schedule["charge_2_mw"]
    discharged = schedule["discharge_1_mw"] + schedule["discharge_2_mw"]
    delivered = 1.0 - params.discharge_loss

    bought_mwh = float(params.dt * charged.sum())
    delivered_mwh = float(params.dt * delivered * discharged.sum())
    cost_gbp = float(
        params.dt
        * (
            schedule["price_1"] * schedule["charge_1_mw"]
            + schedule["price_2"] * schedule["charge_2_mw"]
        ).sum()
    )
    income_gbp = float(
        params.dt
        * delivered
        * (
            schedule["price_1"] * schedule["discharge_1_mw"]
            + schedule["price_2"] * schedule["discharge_2_mw"]
        ).sum()
    )

    return pd.Series(
        {
            "profit_gbp": float(schedule["revenue_gbp"].sum()),
            "revenue_market_1_gbp": float(schedule["revenue_1_gbp"].sum()),
            "revenue_market_2_gbp": float(schedule["revenue_2_gbp"].sum()),
            "income_gbp": income_gbp,
            "cost_gbp": cost_gbp,
            "energy_bought_mwh": bought_mwh,
            "energy_delivered_mwh": delivered_mwh,
            "mean_buy_price_gbp_per_mwh": _per_mwh(cost_gbp, bought_mwh),
            "mean_sell_price_gbp_per_mwh": _per_mwh(income_gbp, delivered_mwh),
            "cycles_used": float(schedule["cycles"].iloc[-1]),
            "cycle_budget": params.cycle_budget,
            "final_volume_mwh": float(schedule["storage_max_mwh"].iloc[-1]),
            "periods": len(schedule),
            "periods_charging": int((charged > _TOLERANCE).sum()),
            "periods_discharging": int((discharged > _TOLERANCE).sum()),
        }
    )


def _per_mwh(total_gbp: float, energy_mwh: float) -> float:
    """Volume-weighted £/MWh, or NaN when nothing was traded."""
    return total_gbp / energy_mwh if energy_mwh > _TOLERANCE else float("nan")
