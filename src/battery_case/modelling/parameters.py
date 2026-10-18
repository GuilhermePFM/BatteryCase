"""Model parameters derived from the battery spec (§2).

The spec is kept in the units the spreadsheet uses; the conversions the model
needs happen here, once, so the formulation reads like §2 to §4 of the write-up.
"""

from __future__ import annotations

from dataclasses import dataclass

from battery_case.data_models import BatterySpec
from battery_case.modelling.periods import PERIOD_HOURS

#: Half-hourly periods in a calendar year, for pro-rating the cycle budget.
PERIODS_PER_YEAR = int(365.25 * 24 / PERIOD_HOURS)


@dataclass(frozen=True, slots=True)
class ModelParameters:
    """Parameters of the MILP, in the model's own units.

    Mirrors the parameter table of §2: ``dt`` hours per period, loss fractions
    on each side, nominal volume, and the degradation rate as a *fraction* per
    equivalent full cycle (the spreadsheet quotes percent).
    """

    dt: float
    max_charge_mw: float
    max_discharge_mw: float
    nominal_volume_mwh: float
    charge_loss: float
    discharge_loss: float
    degradation_per_cycle: float
    cycle_budget: float

    @property
    def round_trip_efficiency(self) -> float:
        """``(1 - e_c)(1 - e_d)`` — 0.9025 for the spec as given (§4.2)."""
        return (1.0 - self.charge_loss) * (1.0 - self.discharge_loss)

    @classmethod
    def from_spec(
        cls,
        spec: BatterySpec,
        *,
        cycle_budget: float | None = None,
        dt: float = PERIOD_HOURS,
    ) -> ModelParameters:
        """Build the parameters from Attachment 1.

        ``cycle_budget`` defaults to the battery's full cycle life, per §5: the
        brief asks for the profit obtainable over this data, not a valuation
        over the asset's ten calendar years. Pass
        :func:`prorated_cycle_budget` for the alternative reading.
        """
        return cls(
            dt=dt,
            max_charge_mw=spec.max_charge_rate_mw,
            max_discharge_mw=spec.max_discharge_rate_mw,
            nominal_volume_mwh=spec.max_storage_volume_mwh,
            charge_loss=spec.charging_loss_fraction,
            discharge_loss=spec.discharging_loss_fraction,
            degradation_per_cycle=spec.degradation_pct_per_cycle / 100.0,
            cycle_budget=spec.lifetime_cycles if cycle_budget is None else cycle_budget,
        )


def prorated_cycle_budget(spec: BatterySpec, periods: int) -> float:
    """Cycle life pro-rated to the share of the battery's calendar life covered.

    The alternative to spending the whole cycle life inside the price data
    (§5): three years of prices against a ten-year life gives 1,500 cycles.
    """
    years = periods / PERIODS_PER_YEAR
    return float(spec.lifetime_cycles * min(years / spec.lifetime_years, 1.0))
