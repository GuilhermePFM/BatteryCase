"""The rolling-window driver and the schedule it produces."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from battery_case.modelling.grid import DispatchGrid
from battery_case.modelling.milp import solve_window
from battery_case.modelling.parameters import ModelParameters, prorated_cycle_budget
from battery_case.modelling.pricers import calibrate_cycle_price
from battery_case.modelling.rolling import RollingDispatcher
from battery_case.modelling.schedule import COLUMNS, summarise
from tests.helpers import SPEC, TOLERANCE, assert_feasible, hourly_mean, make_grid

#: Two days of a repeating cheap-night / dear-evening shape.
_DAY = [20.0] * 16 + [40.0] * 16 + [120.0] * 8 + [60.0] * 8


def _grid(days: int = 2) -> DispatchGrid:
    """``days`` repetitions of a cheap-night / dear-evening shape."""
    half_hourly = _DAY * days
    return make_grid(half_hourly, hourly_mean(half_hourly))


def _overnight_grid() -> DispatchGrid:
    """Two days whose only worthwhile spread sits either side of midnight."""
    half_hourly = [100.0] * 40 + [20.0] * 8 + [250.0] * 8 + [100.0] * 40
    return make_grid(half_hourly, hourly_mean(half_hourly))


def test_schedule_has_the_documented_shape() -> None:
    grid = _grid(1)
    schedule = RollingDispatcher(lookahead_periods=0).run_on_grid(
        grid, ModelParameters.from_spec(SPEC)
    )

    assert list(schedule.columns) == list(COLUMNS)
    assert schedule.index.equals(grid.timestamps)


def test_a_rolling_schedule_satisfies_every_constraint() -> None:
    params = ModelParameters.from_spec(SPEC)
    schedule = RollingDispatcher().run_on_grid(_grid(3), params)

    assert_feasible(schedule, params)


def test_one_window_covering_the_grid_matches_the_undecomposed_solve() -> None:
    """With no decomposition the driver must reproduce the MILP exactly."""
    grid, params = _grid(1), ModelParameters.from_spec(SPEC)
    schedule = RollingDispatcher(commit_periods=len(grid), lookahead_periods=0).run_on_grid(
        grid, params
    )
    solution = solve_window(grid, params)

    np.testing.assert_allclose(schedule["storage_mwh"], solution.storage_mwh, atol=1e-6)
    np.testing.assert_allclose(schedule["cycles"], solution.cycles, atol=1e-6)


def test_the_state_of_charge_carries_across_window_boundaries() -> None:
    """A window handing on a part-charged battery is the point of the handover."""
    params = ModelParameters.from_spec(SPEC)
    # Six-hour windows cut the daily shape up, so some boundary is crossed charged.
    schedule = RollingDispatcher(commit_periods=12, lookahead_periods=12).run_on_grid(
        _grid(2), params
    )

    assert_feasible(schedule, params)
    assert schedule["storage_mwh"].iloc[11] > 1e-6


def test_lookahead_is_discarded_not_committed() -> None:
    """The lookahead changes the committed decisions without extending them.

    The spread here straddles midnight: the cheap periods close day one and the
    dear ones open day two. A day solved alone cannot see the sale, so it does
    not buy; a day solved with tomorrow in view buys and carries the energy over.
    """
    params = ModelParameters.from_spec(SPEC)
    grid = _overnight_grid()
    myopic = RollingDispatcher(commit_periods=48, lookahead_periods=0).run_on_grid(grid, params)
    foresighted = RollingDispatcher(commit_periods=48, lookahead_periods=48).run_on_grid(
        grid, params
    )

    assert len(myopic) == len(foresighted) == len(grid)
    assert myopic["storage_mwh"].iloc[47] == pytest.approx(0.0, abs=1e-6)
    assert foresighted["storage_mwh"].iloc[47] > 1e-6
    assert summarise(foresighted, params)["profit_gbp"] > summarise(myopic, params)["profit_gbp"]


def test_profit_is_income_less_cost() -> None:
    params = ModelParameters.from_spec(SPEC)
    schedule = RollingDispatcher().run_on_grid(_grid(2), params)
    figures = summarise(schedule, params)

    assert figures["profit_gbp"] == pytest.approx(figures["income_gbp"] - figures["cost_gbp"])
    assert figures["profit_gbp"] == pytest.approx(
        figures["revenue_market_1_gbp"] + figures["revenue_market_2_gbp"]
    )
    assert figures["profit_gbp"] > 0
    assert figures["mean_sell_price_gbp_per_mwh"] > figures["mean_buy_price_gbp_per_mwh"]


def test_an_ample_cycle_budget_needs_no_cycle_price() -> None:
    grid, params = _grid(2), ModelParameters.from_spec(SPEC)
    price, schedule = calibrate_cycle_price(grid, params)

    assert price == 0.0
    assert schedule["cycles"].iloc[-1] <= params.cycle_budget


def test_a_binding_cycle_budget_is_rationed_by_a_cycle_price() -> None:
    """One cycle to spend, and the best spread of the three days on the last one.

    The dear day sits beyond the lookahead, so the early windows cannot see it
    and spend part of the cycle on their own modest spreads. Charging for the
    cycle makes them abstain and leaves the whole budget for the day that pays
    most for it — what the budget's shadow price is for.
    """
    cheap = [20.0] * 24
    modest_day = cheap + [100.0] * 24
    dear_day = cheap + [400.0] * 24
    grid = make_grid(modest_day * 2 + dear_day)
    params = replace(ModelParameters.from_spec(SPEC), cycle_budget=1.0)

    unpriced = RollingDispatcher().run_on_grid(grid, params)
    assert unpriced["cycles"].iloc[47] > TOLERANCE
    assert unpriced["cycles"].iloc[-1] == pytest.approx(params.cycle_budget, rel=1e-4)

    price, schedule = calibrate_cycle_price(grid, params, upper_bound=5_000.0)

    assert price > 0.0
    # The modest days abstain, and the budget is still spent in full, on the dear day.
    assert schedule["cycles"].iloc[95] == pytest.approx(0.0, abs=TOLERANCE)
    assert schedule["cycles"].iloc[-1] == pytest.approx(params.cycle_budget, rel=1e-2)
    assert schedule["revenue_gbp"].sum() > unpriced["revenue_gbp"].sum()
    assert_feasible(schedule, params)


def test_windows_must_be_whole_hours() -> None:
    with pytest.raises(ValueError, match="whole number of hours"):
        RollingDispatcher(commit_periods=3)
    with pytest.raises(ValueError, match="whole number of hours"):
        RollingDispatcher(lookahead_periods=5)
    with pytest.raises(ValueError, match="at least one period"):
        RollingDispatcher(commit_periods=0)


def test_prorating_the_cycle_budget_follows_the_horizon_covered() -> None:
    three_years = int(3 * 365.25 * 48)
    assert prorated_cycle_budget(SPEC, three_years) == pytest.approx(1500.0)
    # Never more than the battery's whole cycle life, however long the horizon.
    assert prorated_cycle_budget(SPEC, 100 * three_years) == pytest.approx(SPEC.lifetime_cycles)
