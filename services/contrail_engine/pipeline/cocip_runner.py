"""CoCiP runner — converts OpenSky tracks to pycontrails Flights and runs CoCiP.

Uses PSFlight for aircraft performance (covers all 15 target aircraft types).
Uses ConstantHumidityScaling(rhi_adj=0.99) for ERA5 data (see DISCREPANCIES.md #5).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class CoCiPResult:
    """Single-flight CoCiP output."""

    flight_id: str
    callsign: str
    airline_icao: str
    aircraft_type: str
    energy_forcing_j: float  # Total energy forcing [J]
    ef_per_km: float  # Energy forcing per great-circle km [J/km]
    cocip_rf_net_mean: float  # Mean net RF along contrail [W/m²]
    contrail_persistent: bool  # Any persistent contrail formed
    n_contrail_waypoints: int  # Number of waypoints with persistent contrails
    n_total_waypoints: int
    fuel_burn_kg: float
    co2_kg: float
    flight_distance_km: float
    cruise_alt_mean_ft: float
    sac_satisfied_frac: float  # Fraction of cruise waypoints satisfying SAC
    raw_output: dict[str, Any] = field(default_factory=dict)


def opensky_track_to_flight(
    icao24: str,
    callsign: str,
    path: list,
    aircraft_type: str,
) -> Any:
    """Convert an OpenSky track (list of TrackPoints) to a pycontrails Flight.

    Parameters
    ----------
    icao24 : str
        ICAO 24-bit address.
    callsign : str
        Flight callsign.
    path : list
        List of TrackPoint objects from opensky_client.
    aircraft_type : str
        ICAO type designator (e.g. "B772").

    Returns
    -------
    pycontrails.core.flight.Flight
    """
    from pycontrails.core.flight import Flight

    records = []
    for wp in path:
        if wp.latitude is None or wp.longitude is None:
            continue
        if wp.on_ground:
            continue
        # Convert barometric altitude from meters to feet for Flight
        alt_ft = wp.baro_altitude_m * 3.28084 if wp.baro_altitude_m else None
        if alt_ft is None or alt_ft < 1000:
            continue
        records.append({
            "longitude": wp.longitude,
            "latitude": wp.latitude,
            "altitude": wp.baro_altitude_m,  # Flight expects meters
            "time": pd.Timestamp(wp.time, unit="s", tz="UTC"),
        })

    if len(records) < 5:
        logger.warning("Track %s has only %d valid points, skipping", callsign, len(records))
        return None

    df = pd.DataFrame(records)
    df = df.sort_values("time").reset_index(drop=True)

    # Remove duplicates by time
    df = df.drop_duplicates(subset="time", keep="first").reset_index(drop=True)

    flight = Flight(
        data=df,
        attrs={
            "flight_id": f"{callsign}_{icao24}",
            "icao24": icao24,
            "callsign": callsign,
            "aircraft_type": aircraft_type,
        },
    )
    return flight


def run_cocip_single(
    flight: Any,
    met: Any,
    rad: Any,
    aircraft_type: str,
) -> CoCiPResult | None:
    """Run CoCiP on a single flight.

    Parameters
    ----------
    flight : pycontrails.core.flight.Flight
        Flight trajectory.
    met : MetDataset
        ERA5 pressure-level meteorological data.
    rad : MetDataset
        ERA5 single-level radiation data.
    aircraft_type : str
        ICAO type designator.

    Returns
    -------
    CoCiPResult or None if CoCiP fails.
    """
    from pycontrails.models.cocip import Cocip
    from pycontrails.models.humidity_scaling import ConstantHumidityScaling
    from pycontrails.models.ps_model import PSFlight

    callsign = flight.attrs.get("callsign", "unknown")
    flight_id = flight.attrs.get("flight_id", callsign)
    airline_icao = callsign[:3] if len(callsign) >= 3 else ""

    try:
        cocip = Cocip(
            met=met,
            rad=rad,
            aircraft_performance=PSFlight(),
            humidity_scaling=ConstantHumidityScaling(rhi_adj=0.99),
            aircraft_type=aircraft_type,
        )
        output = cocip.eval(source=flight)
    except Exception:
        logger.exception("CoCiP failed for %s", callsign)
        return None

    # Extract results from CoCiP output
    source = output.source
    contrail = output.contrail

    # Energy forcing
    ef = float(source["ef"].sum()) if "ef" in source else 0.0

    # Flight distance
    dist_km = float(flight.length()) / 1000.0 if hasattr(flight, "length") else 0.0
    ef_per_km = ef / dist_km if dist_km > 0 else 0.0

    # Net radiative forcing (mean over contrail waypoints)
    rf_net_mean = 0.0
    n_contrail = 0
    if contrail is not None and len(contrail) > 0:
        if "rf_net" in contrail:
            rf_net_mean = float(contrail["rf_net"].mean())
        n_contrail = len(contrail)

    # Fuel burn
    fuel_kg = float(source["fuel_flow"].sum()) if "fuel_flow" in source else 0.0
    co2_kg = fuel_kg * 3.159  # EI_CO2 from constants.py

    # Persistence check
    persistent = n_contrail > 0

    # Cruise altitude
    alts = source["altitude_ft"] if "altitude_ft" in source else (source["altitude"] * 3.28084 if "altitude" in source else pd.Series([0]))
    cruise_mask = alts > 30000
    cruise_alt_mean = float(alts[cruise_mask].mean()) if cruise_mask.any() else 0.0

    # SAC satisfaction fraction
    sac_frac = 0.0
    if "sac" in source:
        sac_vals = source["sac"]
        n_cruise = int(cruise_mask.sum())
        if n_cruise > 0:
            sac_frac = float((sac_vals[cruise_mask] > 0).sum()) / n_cruise

    return CoCiPResult(
        flight_id=flight_id,
        callsign=callsign,
        airline_icao=airline_icao,
        aircraft_type=aircraft_type,
        energy_forcing_j=ef,
        ef_per_km=ef_per_km,
        cocip_rf_net_mean=rf_net_mean,
        contrail_persistent=persistent,
        n_contrail_waypoints=n_contrail,
        n_total_waypoints=len(source),
        fuel_burn_kg=fuel_kg,
        co2_kg=co2_kg,
        flight_distance_km=dist_km,
        cruise_alt_mean_ft=cruise_alt_mean,
        sac_satisfied_frac=sac_frac,
        raw_output={
            "ef": ef,
            "n_contrail": n_contrail,
        },
    )


def run_cocip_batch(
    flights: list[tuple[Any, str]],
    met: Any,
    rad: Any,
) -> list[CoCiPResult]:
    """Run CoCiP on a batch of flights.

    Parameters
    ----------
    flights : list of (Flight, aircraft_type) tuples
    met, rad : MetDataset
        Shared meteorological data.

    Returns
    -------
    list[CoCiPResult]
    """
    results = []
    for i, (flight, atype) in enumerate(flights):
        cs = flight.attrs.get("callsign", f"flight_{i}")
        logger.info("Running CoCiP %d/%d: %s (%s)", i + 1, len(flights), cs, atype)
        result = run_cocip_single(flight, met, rad, atype)
        if result is not None:
            results.append(result)
    logger.info("CoCiP batch complete: %d/%d succeeded", len(results), len(flights))
    return results
