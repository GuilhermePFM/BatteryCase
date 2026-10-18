"""The window MILP against the formulation it implements (§3 to §4.7)."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pulp
import pytest

from battery_case.modelling.parameters import ModelParameters
from battery_case.modelling.variables import BatteryState
from battery_case.modelling.window_problem import default_solver, solve_window
from tests.helpers import SPEC, make_periods


@pytest.fixture(scope="module")
def solver() -> pulp.LpSolver:
    """One solver for the module: building it per test dominates these solves."""
    return default_solver()


def _params(*, cycle_budget: float | None = None) -> ModelParameters:
    return ModelParameters.from_spec(SPEC, cycle_budget=cycle_budget)


def test_flat_prices_leave_the_battery_idle(solver: pulp.LpSolver) -> None:
    """With no spread there is nothing to pay for the round-trip loss."""
    settlement = make_periods([50.0] * 8, [50.0] * 4)
    solution = solve_window(settlement, _params(), solver=solver)

    assert solution.storage_mwh.max() == pytest.approx(0.0, abs=1e-6)
    assert solution.cycles[-1] == pytest.approx(0.0, abs=1e-6)


def test_a_spread_below_the_round_trip_loss_is_not_traded(solver: pulp.LpSolver) -> None:
    """11% of spread is needed to cover ``(1 - e_c)(1 - e_d) = 0.9025`` (§4.2)."""
    params = _params()
    assert params.round_trip_efficiency == pytest.approx(0.9025)

    settlement = make_periods([100.0] * 4 + [105.0] * 4, [100.0, 100.0, 105.0, 105.0])
    solution = solve_window(settlement, params, solver=solver)

    assert solution.cycles[-1] == pytest.approx(0.0, abs=1e-6)


def test_the_battery_buys_cheap_and_sells_dear_within_its_limits(solver: pulp.LpSolver) -> None:
    settlement = make_periods([10.0] * 4 + [200.0] * 4, [10.0, 10.0, 200.0, 200.0])
    solution = solve_window(settlement, _params(), solver=solver)

    charged = solution.charge_1_mw + solution.charge_2_mw
    discharged = solution.discharge_1_mw + solution.discharge_2_mw

    # It charges at the rate limit through the whole cheap half and sells nothing,
    np.testing.assert_allclose(charged[:4], SPEC.max_charge_rate_mw, atol=1e-6)
    assert discharged[:4].max() == pytest.approx(0.0, abs=1e-6)
    # keeping (1 - e_c) of the energy imported over those four half hours,
    stored_mwh = 0.5 * 0.95 * charged[:4].sum()
    assert solution.storage_mwh[3] == pytest.approx(stored_mwh, abs=1e-6)
    # and empties the store again in the dear half.
    assert 0.5 * discharged[4:].sum() == pytest.approx(stored_mwh, abs=1e-6)
    assert solution.storage_mwh[-1] == pytest.approx(0.0, abs=1e-6)


def test_rate_and_volume_limits_hold(solver: pulp.LpSolver) -> None:
    prices = [10.0, 10.0, 10.0, 10.0, 300.0, 300.0, 300.0, 300.0] * 3
    settlement = make_periods(prices, prices[::2])
    solution = solve_window(settlement, _params(), solver=solver)

    assert (solution.charge_1_mw + solution.charge_2_mw).max() <= SPEC.max_charge_rate_mw + 1e-6
    assert (
        solution.discharge_1_mw + solution.discharge_2_mw
    ).max() <= SPEC.max_discharge_rate_mw + 1e-6
    assert solution.storage_mwh.max() <= SPEC.max_storage_volume_mwh + 1e-6
    assert solution.storage_mwh.min() >= -1e-6


def test_charging_and_discharging_never_coincide(solver: pulp.LpSolver) -> None:
    """§4.3. Without the binary, buying in Market 1 to sell into Market 2 in the
    same period would be free money whenever the spread covers the loss."""
    settlement = make_periods([10.0] * 8, [300.0] * 4)
    solution = solve_window(settlement, _params(), solver=solver)

    charged = solution.charge_1_mw + solution.charge_2_mw
    discharged = solution.discharge_1_mw + solution.discharge_2_mw
    assert np.minimum(charged, discharged).max() == pytest.approx(0.0, abs=1e-6)


def test_market_2_is_held_constant_across_each_hour(solver: pulp.LpSolver) -> None:
    """§4.5. The second half hour of each Market 2 hour is the cheap one, but
    the commitment is hourly, so a half-hour-only trade is not available."""
    settlement = make_periods([80.0, 20.0] * 4, [60.0] * 4)
    solution = solve_window(settlement, _params(), solver=solver)

    np.testing.assert_allclose(solution.charge_2_mw[0::2], solution.charge_2_mw[1::2], atol=1e-6)
    np.testing.assert_allclose(
        solution.discharge_2_mw[0::2], solution.discharge_2_mw[1::2], atol=1e-6
    )


def test_market_1_is_free_to_move_within_the_hour(solver: pulp.LpSolver) -> None:
    settlement = make_periods([300.0, 10.0] + [10.0] * 2 + [300.0] * 4, [60.0] * 4)
    solution = solve_window(settlement, _params(), BatteryState(storage_mwh=2.0), solver=solver)

    # It sells into the dear first half hour and not the cheap second one.
    assert solution.discharge_1_mw[0] > 1e-6
    assert solution.discharge_1_mw[1] == pytest.approx(0.0, abs=1e-6)


def test_cycles_are_counted_on_discharge_only(solver: pulp.LpSolver) -> None:
    """§4.6. Charging without discharging consumes no cycle life."""
    settlement = make_periods([10.0] * 4 + [60.0] * 4, [10.0, 10.0, 60.0, 60.0])
    solution = solve_window(settlement, _params(), solver=solver)

    discharged = solution.discharge_1_mw + solution.discharge_2_mw
    first_discharge = int(np.argmax(discharged > 1e-6))
    assert first_discharge > 0, "the cheap half should charge before anything is sold"
    assert solution.cycles[:first_discharge].max() == pytest.approx(0.0, abs=1e-6)

    throughput_mwh = 0.5 * discharged.sum()
    assert solution.cycles[-1] == pytest.approx(throughput_mwh / SPEC.max_storage_volume_mwh)


def test_the_cycle_budget_caps_throughput(solver: pulp.LpSolver) -> None:
    settlement = make_periods([10.0] * 4 + [300.0] * 4, [10.0, 10.0, 300.0, 300.0])
    params = _params(cycle_budget=0.25)
    solution = solve_window(settlement, params, solver=solver)

    assert solution.cycles[-1] <= 0.25 + 1e-6
    assert 0.5 * (solution.discharge_1_mw + solution.discharge_2_mw).sum() == pytest.approx(
        0.25 * SPEC.max_storage_volume_mwh, abs=1e-6
    )


def test_degradation_shrinks_the_usable_volume(solver: pulp.LpSolver) -> None:
    """§4.7. A battery carrying cycles cannot refill to the nominal volume."""
    settlement = make_periods([10.0] * 4 + [300.0] * 4, [10.0, 10.0, 300.0, 300.0])
    params = replace(_params(), degradation_per_cycle=0.1)
    solution = solve_window(settlement, params, BatteryState(cycles=2.0), solver=solver)

    usable = SPEC.max_storage_volume_mwh * (1 - 0.1 * 2.0)
    assert solution.storage_mwh.max() <= usable + 1e-6
    assert solution.storage_mwh.max() == pytest.approx(usable, abs=1e-6)


def test_the_opening_state_is_carried_into_the_balance(solver: pulp.LpSolver) -> None:
    """§4.2. A window starting part-charged can sell before it buys."""
    settlement = make_periods([300.0] * 2 + [10.0] * 6, [300.0, 10.0, 10.0, 10.0])
    solution = solve_window(settlement, _params(), BatteryState(storage_mwh=4.0), solver=solver)

    assert solution.discharge_1_mw[0] + solution.discharge_2_mw[0] > 1e-6
    assert solution.storage_mwh[0] < 4.0
