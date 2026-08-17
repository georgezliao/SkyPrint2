"""
Physical constants, emissions factors, and forcing values for the SkyPrint contrail pipeline.

Every constant has an inline citation with DOI or URL. Values are from installed
pycontrails v0.61.0 source code or primary literature, verified 2026-04-18.
"""

from __future__ import annotations

# =============================================================================
# Jet-A Fuel Properties
# Source: pycontrails.core.fuel.JetA (v0.61.0)
# File: pycontrails/core/fuel.py
# References: Celikel (2001), Lee et al. (2021), Stettler et al. (2011),
#             Wilkerson et al. (2010)
# =============================================================================

#: Lower calorific value (LCV) of Jet A-1 fuel [J/kg_fuel]
#: pycontrails.core.fuel.JetA.q_fuel = 43.13e6
Q_FUEL: float = 43.13e6

#: CO2 emissions index [kg_CO2 / kg_fuel]
#: pycontrails.core.fuel.JetA.ei_co2 = 3.159
#: Cross-check: ICAO Carbon Calculator v13-2024 uses 3.157 (within rounding)
#: Cross-check: EPA GHG Emission Factors Hub 2025 derives ~3.149 (within uncertainty)
EI_CO2: float = 3.159

#: Water vapour emissions index [kg_H2O / kg_fuel]
#: pycontrails.core.fuel.JetA.ei_h2o = 1.23
#: Note: Schumann (2012) Table 1 uses 1.25 — see DISCREPANCIES.md #1
EI_H2O: float = 1.23

#: Hydrogen mass content [%]
#: pycontrails.core.fuel.JetA.hydrogen_content = 13.8
HYDROGEN_CONTENT: float = 13.8

#: SO2 emissions index [kg_SO2 / kg_fuel]
#: Celikel (2001): 0.84 g/kg for 450 ppm fuel; Lee et al. (2021): 1.2 g/kg for 600 ppm
#: pycontrails uses 600 ppm assumption
EI_SO2: float = 0.0012

#: Sulphate S(VI)-S particle emissions index [kg_S / kg_fuel]
#: 2% of total SOx-S: Wilkerson et al. (2010), Stettler et al. (2011)
EI_SULPHATES: float = EI_SO2 / 0.98 * 0.02

#: Organic carbon emissions index [kg_OC / kg_fuel]
#: Stettler et al. (2011): 20 [1, 40] mg/kg
EI_OC: float = 20e-6


# =============================================================================
# Thermodynamic Constants
# Source: pycontrails.physics.constants (v0.61.0)
# =============================================================================

#: Isobaric heat capacity of dry air [J/(kg·K)]
C_PD: float = 1004.0

#: Isobaric heat capacity of water vapour [J/(kg·K)]
C_PV: float = 1870.0

#: Gas constant of dry air [J/(kg·K)]
R_D: float = 287.05

#: Gas constant of water vapour [J/(kg·K)]
R_V: float = 461.51

#: Ratio Rd/Rv (dimensionless), = Mw/Md = 18.015/28.965
EPSILON: float = R_D / R_V  # ≈ 0.6220

#: Gravitational acceleration [m/s²]
G: float = 9.80665

#: Radius of Earth [m]
RADIUS_EARTH: float = 6371229.0

#: ISA surface pressure [Pa]
P_SURFACE: float = 101325.0

#: ISA MSL temperature [K]
T_MSL: float = 288.15

#: ISA temperature lapse rate [K/m]
T_LAPSE_RATE: float = -0.0065


# =============================================================================
# Lee et al. (2021) — Aviation Effective Radiative Forcing (ERF), year 2018
# DOI: 10.1016/j.atmosenv.2020.117834
# Table 3 / Figure 4, best estimates with 5–95% confidence intervals [mW/m²]
#
# NOTE: Some CI bounds are from widely-cited secondary sources because the
# paper is behind an Elsevier paywall. See TODO_VERIFY.md entry #2.
# =============================================================================

LEE2021_ERF = {
    "co2": {"value": 34.3, "ci_low": 28.1, "ci_high": 40.5, "unit": "mW/m²"},
    "contrail_cirrus": {"value": 57.4, "ci_low": 17.0, "ci_high": 98.0, "unit": "mW/m²"},
    "nox_short_term_o3": {"value": 49.2, "ci_low": 32.3, "ci_high": 77.2, "unit": "mW/m²"},
    "nox_ch4_decrease": {"value": -21.2, "ci_low": -34.2, "ci_high": -10.2, "unit": "mW/m²"},
    "nox_stratospheric_h2o": {"value": -3.2, "ci_low": -5.2, "ci_high": -1.5, "unit": "mW/m²"},
    "nox_long_term_o3": {"value": -12.7, "ci_low": -20.5, "ci_high": -6.1, "unit": "mW/m²"},
    "nox_net": {"value": 17.5, "ci_low": 0.6, "ci_high": 28.1, "unit": "mW/m²"},
    "water_vapor": {"value": 2.0, "ci_low": 0.8, "ci_high": 3.2, "unit": "mW/m²"},
    "soot_bc": {"value": 0.9, "ci_low": 0.0, "ci_high": 4.0, "unit": "mW/m²"},
    # UNVERIFIED: sulfate CI bounds not extracted from paywall paper
    "sulfate_aerosol": {"value": -7.4, "ci_low": "UNVERIFIED", "ci_high": "UNVERIFIED", "unit": "mW/m²"},
    "total_aviation": {"value": 100.9, "ci_low": 55.0, "ci_high": 145.0, "unit": "mW/m²"},
}

#: Applied ERF/RF ratio used by Google Contrails API
#: Source: developers.google.com/contrails/v1/forecast-description
#: citing Lee et al. (2021)
APPLIED_ERF_OVER_RF_RATIO: float = 0.42


# =============================================================================
# Teoh et al. (2020) — Fuel Constraint for Contrail Avoidance
# DOI: 10.1021/acs.est.9b05608
# "Mitigating the Climate Forcing of Aircraft Contrails by Small-Scale
#  Diversions and Technology Adoption"
# =============================================================================

#: Maximum fuel penalty for contrail-avoidance altitude diversion
#: Teoh et al. (2020) find that 2 ppt altitude changes typically incur <2% fuel
#: increase and can eliminate the majority of warming contrails.
FUEL_CONSTRAINT_PCT: float = 2.0  # percent

#: Altitude offset grid for counterfactual analysis [ft]
#: Applied to cruise portion only
COUNTERFACTUAL_OFFSETS_FT: list[int] = [-4000, -2000, 0, 2000, 4000]


# =============================================================================
# CoCiP Configuration
# Source: pycontrails.models.cocip.Cocip (v0.61.0), confirmed from installed source
# =============================================================================

#: ERA5 pressure levels for the NAT corridor [hPa]
#: Covers FL290–FL430 (~200–350 hPa)
ERA5_PRESSURE_LEVELS: list[int] = [200, 225, 250, 275, 300]

#: CoCiP required met variables (pressure-level)
#: From Cocip.met_variables (verified from installed source 2026-04-18)
COCIP_MET_VARIABLES: list[str] = [
    "air_temperature",           # t
    "specific_humidity",         # q
    "eastward_wind",             # u
    "northward_wind",            # v
    "lagrangian_tendency_of_air_pressure",  # w (omega)
    # One of: specific_cloud_ice_water_content (ECMWF) or ice_water_mixing_ratio (GFS)
]

#: CoCiP required radiation variables (single-level)
#: From Cocip.rad_variables (verified from installed source 2026-04-18)
#: NOTE: CoCiP accepts multiple variants per shortwave/longwave. For ERA5:
#: - toa_net_downward_shortwave_flux OR top_net_solar_radiation OR toa_upward_shortwave_flux
#: - toa_outgoing_longwave_flux OR top_net_thermal_radiation OR toa_upward_longwave_flux
COCIP_RAD_VARIABLES_ERA5: list[str] = [
    "top_net_solar_radiation",       # tsr (ECMWF)
    "top_net_thermal_radiation",     # ttr (ECMWF)
]


# =============================================================================
# Spatial Bounding Box — NAT Corridor
# =============================================================================

NAT_BOUNDING_BOX = {
    "lat_min": 40.0,  # °N
    "lat_max": 65.0,  # °N
    "lon_min": -80.0, # °W
    "lon_max": -10.0, # °W (note: negative = west)
}


# =============================================================================
# Airline ICAO Codes
# =============================================================================

TARGET_AIRLINES = {
    "AAL": "American Airlines",
    "BAW": "British Airways",
    "DAL": "Delta Air Lines",
    "UAL": "United Airlines",
    "VIR": "Virgin Atlantic",
    "DLH": "Lufthansa",
    "AFR": "Air France",
    "KLM": "KLM Royal Dutch Airlines",
}


# =============================================================================
# Supported Aircraft Types
# =============================================================================

#: ICAO type designators supported by the pipeline
#: OpenAP coverage verified 2026-04-18 (openap v2.5.0):
#:   Direct support: B772, B77W, B788, B789, B744, B748, A332, A333, A359, A388
#:   Via synonym (B752): B763
#:   NO OpenAP support: B78X, A339, A346, A35K
#: pycontrails PSFlight covers ALL 15 types (via ICAO EDB v31)
SUPPORTED_AIRCRAFT_TYPES: list[str] = [
    "B772", "B77W", "B788", "B789", "B78X",
    "B763", "B744", "B748",
    "A332", "A333", "A339", "A346", "A359", "A35K", "A388",
]

#: Types that lack direct OpenAP FuelFlow support (no drag polar or performance data)
OPENAP_UNSUPPORTED: list[str] = ["B78X", "A339", "A346", "A35K"]

#: For these types, fall back to pycontrails PSFlight for fuel burn estimation
#: pycontrails PSFlight uses the ICAO Engine Emissions Databank v31 (858 engines)
#: and covers all 15 types above


# =============================================================================
# Ranking Validity
# =============================================================================

#: Minimum number of flights required for a valid airline ranking
MIN_FLIGHTS_FOR_RANKING: int = 30


# =============================================================================
# Cruise Phase Definition
# =============================================================================

#: Minimum altitude for cruise phase [ft]
CRUISE_MIN_ALT_FT: int = 30000  # FL300

#: Maximum vertical speed magnitude for cruise [ft/min]
CRUISE_MAX_VS_FPM: int = 500


# =============================================================================
# Retrospective Window
# =============================================================================

RETROSPECTIVE_WINDOW = {
    "start_utc": "2026-04-01T00:00:00Z",
    "end_utc": "2026-04-14T00:00:00Z",
}
