"""The plan frame and the figures read off it."""

from __future__ import annotations

import numpy as np
import pytest

from battery_case.modelling.parameters import ModelParameters
from battery_case.modelling.plan import COLUMNS, build_plan, effective_volume, summarise
from tests.helpers import SPEC, make_periods


def _schedule(**decisions: np.ndarray):  # type: ignore[no-untyped-def]
    settlement = make_periods([50.0, 60.0, 70.0, 80.0])
    zeros = np.zeros(len(settlement))
    arrays = {
        "charge_1_mw": zeros,
        "charge_2_mw": zeros,
        "discharge_1_mw": zeros,
        "discharge_2_mw": zeros,
        "storage_mwh": zeros,
        "cycles": zeros,
        **decisions,
    }
    return settlement, build_plan(settlement, ModelParameters.from_spec(SPEC), **arrays)


def test_revenue_prices_energy_delivered_not_energy_drawn() -> None:
    """§3. Only ``(1 - e_d)`` of what leaves the store is paid for."""
    discharge = np.array([2.0, 0.0, 0.0, 0.0])
    settlement, plan = _schedule(discharge_1_mw=discharge)

    expected = 0.5 * settlement.price_1[0] * 0.95 * 2.0
    assert plan["net_revenue_1_gbp"].iloc[0] == pytest.approx(expected)
    assert plan["net_revenue_gbp"].sum() == pytest.approx(expected)


def test_charging_is_paid_at_the_full_imported_power() -> None:
    """§3. The charge loss is taken in the store, not in the price paid."""
    charge = np.array([2.0, 0.0, 0.0, 0.0])
    settlement, plan = _schedule(charge_1_mw=charge)

    assert plan["net_revenue_1_gbp"].iloc[0] == pytest.approx(-0.5 * settlement.price_1[0] * 2.0)


def test_solver_noise_is_reported_as_zero() -> None:
    """A MILP is solved to a tolerance, so a variable held at zero may come
    back at 1e-6. Left in, it reads as charging and discharging at once (§4.3)."""
    _, plan = _schedule(
        charge_1_mw=np.array([1e-6, -0.0, 0.0, 0.0]),
        discharge_2_mw=np.array([0.95, 0.95, 0.0, 0.0]),
    )

    charged = plan["charge_1_mw"] + plan["charge_2_mw"]
    discharged = plan["discharge_1_mw"] + plan["discharge_2_mw"]
    assert np.minimum(charged, discharged).max() == 0.0
    # Signed zeros are normalised too, so the plan prints no "-0.0".
    assert (np.sign(plan["charge_1_mw"]) >= 0).all()


def test_effective_volume_follows_the_cycles_accumulated() -> None:
    """§4.7. At the 5,000-cycle limit the loss is 5% of the nominal volume."""
    params = ModelParameters.from_spec(SPEC)
    volumes = effective_volume(params, np.array([0.0, 2500.0, 5000.0]))

    # rho = 1e-5 per cycle, so 2.5% of the volume at half the cycle life and 5%
    # at all of it — the figure §4.7 quotes.
    np.testing.assert_allclose(volumes, [4.0, 3.9, 3.8])


def test_summary_reports_nan_prices_when_nothing_is_traded() -> None:
    params = ModelParameters.from_spec(SPEC)
    _, plan = _schedule()
    figures = summarise(plan, params)

    assert figures["profit_gbp"] == 0.0
    assert np.isnan(figures["mean_buy_price_gbp_per_mwh"])
    assert np.isnan(figures["mean_sell_price_gbp_per_mwh"])
    assert figures["periods_charging"] == 0
    assert list(plan.columns) == list(COLUMNS)


def test_summary_separates_closing_storage_from_remaining_capacity() -> None:
    """The two closing figures answer different questions (§4.7, §7).

    ``final_storage_mwh`` is what is left in the store; ``final_usable_volume_mwh``
    is how much the store could still hold after the cycles spent degrading it.
    """
    params = ModelParameters.from_spec(SPEC)
    _, plan = _schedule(
        storage_mwh=np.array([1.0, 2.0, 1.5, 0.75]),
        cycles=np.array([0.0, 0.0, 100.0, 200.0]),
    )
    figures = summarise(plan, params)

    assert figures["final_storage_mwh"] == 0.75
    # rho = 1e-5 per cycle over 200 cycles: 0.2% off the 4 MWh nominal volume.
    assert figures["final_usable_volume_mwh"] == pytest.approx(3.992)
    assert figures["final_storage_mwh"] < figures["final_usable_volume_mwh"]
