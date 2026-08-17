"""Route geometry computation for historical flights.

Derives the actual-flown and contrail-optimal geometry for an OpenSky track,
using SAC-based altitude optimisation and Open-Meteo weather. CoCiP / ERA5 are
NOT used here because ERA5 is not available on demand for arbitrary past dates.
Use the batch pipeline (pipeline/counterfactual.py) for ERA5-backed analysis.

The "optimal path" keeps the same lat/lon as the original; it only shifts cruise
altitudes to avoid persistent contrail formation, within the 2 % fuel constraint
from Teoh et al. 2020 (doi:10.1021/acs.est.9b05608).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 0.4 % fuel per 1 000 ft altitude change — conservative bound derived from the
# Teoh 2020 finding that typical diversions incur < 2 % fuel increase.
_FUEL_PCT_PER_1000FT: float = 0.4


@dataclass
class RouteGeometryWaypoint:
    time_unix: int
    latitude: float
    longitude: float
    altitude_ft: float
    contrail_risk: bool


@dataclass
class RouteGeometryResult:
    flight_id: str
    callsign: str
    icao24: str
    aircraft_type: str

    # Coordinate arrays for both paths — same lat/lon, altitude differs at
    # contrail-forming cruise waypoints.
    original_path: list[RouteGeometryWaypoint]
    optimal_path: list[RouteGeometryWaypoint]

    # Per-passenger CO2 (ICAO polynomial method, great-circle distance).
    co2_kg_original: float
    co2_kg_optimal: float
    co2_kg_delta: float   # positive: optimal uses slightly more fuel

    n_contrail_waypoints: int  # cruise waypoints where contrail was detected
    n_total_waypoints: int
    fuel_penalty_pct: float    # estimated; ≤ 2 % by construction
    ef_reduction_pct: float    # fraction of contrail waypoints eliminated
    avoidable: bool            # True if any contrail-forming waypoint has a fix

    # Always True when called from the HTTP endpoint; False only in batch pipeline
    used_sac_fallback: bool = True


def build_route_geometry(
    original_waypoints: list,
    optimal_waypoints: list,
    adjustments: list[dict],
    contrail_flags: list[bool],
    aircraft_type_str: str,
    callsign: str,
    icao24: str,
    co2_original: float,
) -> RouteGeometryResult:
    """Assemble a RouteGeometryResult from pre-computed optimiser outputs.

    Parameters
    ----------
    original_waypoints:
        app.models.common.Waypoint list for the actual flown track.
    optimal_waypoints:
        Same list with altitude adjustments applied.
    adjustments:
        Output of ``optimize_altitude_profile`` — list of dicts with keys
        ``waypoint_index``, ``original_altitude_ft``, ``suggested_altitude_ft``.
    contrail_flags:
        Boolean per waypoint: True if the original altitude formed a persistent
        contrail.
    co2_original:
        Per-passenger CO2 [kg] for the original route (ICAO method).
    """
    n_total = len(original_waypoints)
    n_contrail = len(adjustments)

    n_cruise = sum(1 for wp in original_waypoints if wp.altitude_ft >= 25000)

    if n_cruise > 0 and adjustments:
        avg_delta_ft = sum(
            abs(a["suggested_altitude_ft"] - a["original_altitude_ft"])
            for a in adjustments
        ) / len(adjustments)
        fuel_penalty_pct = min(
            2.0,
            avg_delta_ft / 1000 * _FUEL_PCT_PER_1000FT * (n_contrail / n_cruise),
        )
    else:
        fuel_penalty_pct = 0.0

    co2_optimal = co2_original * (1.0 + fuel_penalty_pct / 100.0)
    ef_reduction_pct = (n_contrail / n_cruise * 100.0) if n_cruise > 0 else 0.0

    orig_path = [
        RouteGeometryWaypoint(
            time_unix=int(wp.time.timestamp()),
            latitude=wp.latitude,
            longitude=wp.longitude,
            altitude_ft=wp.altitude_ft,
            contrail_risk=contrail_flags[i] if i < len(contrail_flags) else False,
        )
        for i, wp in enumerate(original_waypoints)
    ]

    opt_path = [
        RouteGeometryWaypoint(
            time_unix=int(wp.time.timestamp()),
            latitude=wp.latitude,
            longitude=wp.longitude,
            altitude_ft=wp.altitude_ft,
            contrail_risk=False,
        )
        for wp in optimal_waypoints
    ]

    return RouteGeometryResult(
        flight_id=f"{callsign}_{icao24}",
        callsign=callsign,
        icao24=icao24,
        aircraft_type=aircraft_type_str,
        original_path=orig_path,
        optimal_path=opt_path,
        co2_kg_original=co2_original,
        co2_kg_optimal=round(co2_optimal, 2),
        co2_kg_delta=round(co2_optimal - co2_original, 2),
        n_contrail_waypoints=n_contrail,
        n_total_waypoints=n_total,
        fuel_penalty_pct=round(fuel_penalty_pct, 3),
        ef_reduction_pct=round(ef_reduction_pct, 1),
        avoidable=n_contrail > 0,
    )
