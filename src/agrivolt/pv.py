"""Electricity generation from the array.

Deliberately conventional. The novel part of this project is what happens under
the modules, not the modules themselves, so the PV side sticks to models a
reviewer or a lender's engineer will already accept:

  * bifacial irradiance from pvlib's infinite sheds model, which shares its
    geometry with `shading` so the light budget above and below the array is
    internally consistent
  * Faiman cell temperature, appropriate for the open, elevated, well-ventilated
    mounting an agrivoltaic array uses
  * PVWatts DC conversion with an explicit temperature coefficient

The temperature coefficient matters more here than in the European literature
this field grew out of. A Maharashtra module spends much of the year 25-30 K
above its rating temperature, which costs roughly a tenth of nameplate output.
Elevating the array for tractor clearance improves rear ventilation and claws
some of that back -- an agrivoltaic co-benefit that is easy to forget.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import pandas as pd
import pvlib

from .geometry import PanelArray

WATTS_PER_KW = 1000.0


@dataclass(frozen=True)
class ModuleSpec:
    """Module and balance-of-system electrical characteristics.

    Defaults describe a current bifacial mono-PERC module of the kind an Indian
    EPC would actually quote in 2026.
    """

    gamma_pdc: float = -0.0034      # power temperature coefficient, 1/K
    bifaciality: float = 0.80       # rear-side response relative to front
    albedo: float = 0.23            # crop canopy; bare soil runs higher
    soiling_loss: float = 0.04      # dust, mitigated by Konkan monsoon washing
    mismatch_loss: float = 0.02
    wiring_loss: float = 0.02
    inverter_efficiency: float = 0.98
    availability: float = 0.98      # grid and plant downtime

    @property
    def system_efficiency(self) -> float:
        """Combined derate from DC output to metered AC energy."""
        return (
            (1 - self.soiling_loss)
            * (1 - self.mismatch_loss)
            * (1 - self.wiring_loss)
            * self.inverter_efficiency
            * self.availability
        )


def plane_of_array(irradiance: pd.DataFrame, solar_position: pd.DataFrame,
                   array: PanelArray, module: ModuleSpec) -> pd.Series:
    """Effective bifacial irradiance on the modules, in W/m2."""
    result = pvlib.bifacial.infinite_sheds.get_irradiance(
        surface_tilt=array.tilt,
        surface_azimuth=array.azimuth,
        solar_zenith=solar_position["apparent_zenith"],
        solar_azimuth=solar_position["azimuth"],
        gcr=array.gcr,
        height=array.row_centre_height,
        pitch=array.pitch,
        ghi=irradiance["ghi"],
        dhi=irradiance["dhi"],
        dni=irradiance["dni"],
        albedo=module.albedo,
        bifaciality=module.bifaciality,
    )
    return result["poa_global"].fillna(0.0)


def generation(irradiance: pd.DataFrame, solar_position: pd.DataFrame,
               weather: pd.DataFrame, array: PanelArray, module: ModuleSpec,
               dc_capacity_kw: float) -> pd.Series:
    """Hourly AC energy delivered to the meter, in kWh.

    Input is hourly, so a power in kW over one hour is an energy in kWh.
    """
    poa = plane_of_array(irradiance, solar_position, array, module)
    cell_temperature = pvlib.temperature.faiman(
        poa, weather["temp_air"], weather["wind_speed"]
    )
    dc_watts = pvlib.pvsystem.pvwatts_dc(
        effective_irradiance=poa,
        temp_cell=cell_temperature,
        pdc0=dc_capacity_kw * WATTS_PER_KW,
        gamma_pdc=module.gamma_pdc,
    )
    ac_kwh = (dc_watts / WATTS_PER_KW) * module.system_efficiency
    return ac_kwh.clip(lower=0.0).rename("ac_kwh")


def bifacial_gain(irradiance: pd.DataFrame, solar_position: pd.DataFrame,
                  array: PanelArray, module: ModuleSpec) -> float:
    """Rear-side contribution as a fraction of front-side-only irradiance.

    Worth reporting rather than absorbing into the yield figure. Agrivoltaic
    arrays are wide open and mounted high, which is exactly the geometry that
    maximises rear-side gain, so a specific yield that looks high for the
    location usually has its explanation here rather than in an error.
    """
    with_rear = plane_of_array(irradiance, solar_position, array, module)
    front_only = plane_of_array(
        irradiance, solar_position, array, replace(module, bifaciality=0.0)
    )
    front_total = float(front_only.sum())
    if front_total <= 0:
        return 0.0
    return float(with_rear.sum()) / front_total - 1.0


def specific_yield(annual_kwh: float, dc_capacity_kw: float) -> float:
    """Annual energy per kW installed, in kWh/kWp -- the industry's yardstick."""
    return annual_kwh / dc_capacity_kw
