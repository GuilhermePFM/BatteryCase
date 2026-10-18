"""Shared fixtures for the modelling tests: the spec, grids, and a feasibility check."""

from __future__ import annotations

import numpy as np
import pandas as pd

from battery_case.data_models import BatterySpec, MarketPrices
from battery_case.modelling.parameters import ModelParameters
from battery_case.modelling.periods import PERIODS_PER_HOUR, SettlementPeriods, build_periods

#: Attachment 1 as given, so the tests read against the numbers in the write-up.
SPEC = BatterySpec(
    max_charge_rate_mw=2.0,
    max_discharge_rate_mw=2.0,
    max_storage_volume_mwh=4.0,
    charging_loss_fraction=0.05,
    discharging_loss_fraction=0.05,
    lifetime_years=10.0,
    lifetime_cycles=5000.0,
    degradation_pct_per_cycle=0.001,
    capex_gbp=500_000.0,
    fixed_opex_gbp_per_year=5_000.0,
)

#: Treated as the solver's zero throughout the assertions below (MW, MWh).
TOLERANCE = 1e-6


def make_periods(market_1: list[float], market_2: list[float] | None = None) -> SettlementPeriods:
    """Build a settlement from half-hourly prices, averaging them for Market 2 by default."""
    hourly = market_2 if market_2 is not None else hourly_mean(market_1)
    return build_periods(
        MarketPrices(
            market_1=pd.Series(
                market_1,
                index=pd.date_range("2024-01-01", periods=len(market_1), freq="30min"),
                dtype=float,
            ),
            market_2=pd.Series(
                hourly,
                index=pd.date_range("2024-01-01", periods=len(hourly), freq="1h"),
                dtype=float,
            ),
        )
    )


def hourly_mean(half_hourly: list[float]) -> list[float]:
    """The hourly series implied by a half-hourly one."""
    pairs = zip(half_hourly[0::2], half_hourly[1::2], strict=True)
    return [0.5 * (first + second) for first, second in pairs]


def assert_feasible(plan: pd.DataFrame, params: ModelParameters) -> None:
    """Check a plan against the constraints of §4, period by period."""
    charged = plan["charge_1_mw"] + plan["charge_2_mw"]
    discharged = plan["discharge_1_mw"] + plan["discharge_2_mw"]

    # §4.3 rate limits, and charge or discharge but not both.
    assert charged.max() <= params.max_charge_mw + TOLERANCE
    assert discharged.max() <= params.max_discharge_mw + TOLERANCE
    assert np.minimum(charged, discharged).max() <= TOLERANCE

    # §4.2 energy balance, against the state the previous period left.
    opening = plan["storage_mwh"].shift(1).fillna(0.0)
    expected = opening + params.dt * ((1 - params.charge_loss) * charged - discharged)
    np.testing.assert_allclose(plan["storage_mwh"], expected, atol=TOLERANCE)

    # §4.1 with §4.7: the store never exceeds its degraded volume.
    assert (plan["storage_mwh"] >= -TOLERANCE).all()
    assert (plan["storage_mwh"] <= plan["effective_volume_mwh"] + TOLERANCE).all()

    # §4.5 Market 2 is held across each hour.
    for column in ("charge_2_mw", "discharge_2_mw"):
        values = plan[column].to_numpy()
        np.testing.assert_allclose(
            values[0::PERIODS_PER_HOUR], values[1::PERIODS_PER_HOUR], atol=TOLERANCE
        )

    # §4.6 cycles accumulate on discharge and stay inside the budget.
    expected_cycles = (params.dt * discharged / params.nominal_volume_mwh).cumsum()
    np.testing.assert_allclose(plan["cycles"], expected_cycles, atol=TOLERANCE)
    assert plan["cycles"].iloc[-1] <= params.cycle_budget + TOLERANCE
