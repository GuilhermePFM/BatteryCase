"""Physical and economic description of the battery asset."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BatterySpec:
    """Technical and cost parameters of the battery (Attachment 1).

    Fields mirror the spreadsheet one for one, in the units it uses, so the
    loader stays trivial to audit. Note in particular:

    * the two efficiency rows are *loss fractions* (0.05 = 5% lost);
    * ``degradation_pct_per_cycle`` is in percent, not a fraction.

    Any conversion or derived quantity belongs in the model, not here.
    """

    max_charge_rate_mw: float
    max_discharge_rate_mw: float
    max_storage_volume_mwh: float
    charging_loss_fraction: float
    discharging_loss_fraction: float
    lifetime_years: float
    lifetime_cycles: float
    degradation_pct_per_cycle: float
    capex_gbp: float
    fixed_opex_gbp_per_year: float
