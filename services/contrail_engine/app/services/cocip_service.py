"""PyContrails CoCiP model wrapper.

Wraps the Contrail Cirrus Prediction (CoCiP) model from pycontrails
to predict contrail formation, evolution, and radiative forcing.
"""

import asyncio
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from app.config import settings
from app.models.common import AircraftType, Waypoint
from app.utils.conversions import feet_to_meters

logger = logging.getLogger(__name__)


def _build_flight_dataframe(waypoints: list[Waypoint]) -> pd.DataFrame:
    """Convert API waypoints to a DataFrame suitable for pycontrails."""
    data = {
        "longitude": [wp.longitude for wp in waypoints],
        "latitude": [wp.latitude for wp in waypoints],
        "altitude": [feet_to_meters(wp.altitude_ft) for wp in waypoints],
        "time": [pd.Timestamp(wp.time) for wp in waypoints],
    }
    return pd.DataFrame(data)


async def run_cocip(
    waypoints: list[Waypoint],
    aircraft_type: AircraftType,
    flight_id: str = "unknown",
) -> dict | None:
    """Run the CoCiP model on a flight trajectory.

    Returns prediction results or None if CoCiP is unavailable.
    """
    try:
        from pycontrails import Flight
        from pycontrails.datalib.gfs import GFSForecast
        from pycontrails.models.cocip import Cocip
        from pycontrails.models.humidity_scaling import ConstantHumidityScaling
    except ImportError:
        logger.warning("pycontrails not available, cannot run CoCiP")
        return None

    df = _build_flight_dataframe(waypoints)
    flight = Flight(data=df, flight_id=flight_id, aircraft_type=aircraft_type.value)

    # Determine time bounds for weather data
    times = [wp.time for wp in waypoints]
    time_start = min(times)
    time_end = max(times)

    # Pressure levels covering typical cruise altitudes (FL290-FL430)
    pressure_levels = [150, 175, 200, 225, 250, 300, 350]

    try:
        # Fetch weather data — this is I/O bound, run in thread pool
        def _fetch_weather():
            gfs_met = GFSForecast(
                time=(time_start, time_end),
                variables=Cocip.met_variables,
                pressure_levels=pressure_levels,
                cachestore=settings.weather_cache_dir,
            )
            gfs_rad = GFSForecast(
                time=(time_start, time_end),
                variables=Cocip.rad_variables,
                cachestore=settings.weather_cache_dir,
            )
            met = gfs_met.open_metdataset()
            rad = gfs_rad.open_metdataset()
            return met, rad

        met, rad = await asyncio.to_thread(_fetch_weather)

        # Run CoCiP — CPU bound, run in thread pool
        def _run_model():
            cocip = Cocip(
                met=met,
                rad=rad,
                params={
                    "humidity_scaling": ConstantHumidityScaling(rhi_adj=0.97),
                    "process_emissions": True,
                    "verbose_outputs_evolution": True,
                },
            )
            return cocip.eval(source=flight)

        result_flight = await asyncio.to_thread(_run_model)

        # Extract per-waypoint results
        result_df = result_flight.dataframe
        waypoint_results = []

        for _, row in result_df.iterrows():
            waypoint_results.append({
                "sac_satisfied": bool(row.get("sac", False)),
                "persistent": bool(row.get("persistent", False)),
                "rf_net_w_m2": float(row["rf_net"]) if "rf_net" in row and pd.notna(row["rf_net"]) else None,
                "contrail_age_hours": float(row["contrail_age"]) / 3600 if "contrail_age" in row and pd.notna(row["contrail_age"]) else None,
                "ef_j_per_m": float(row["ef"]) if "ef" in row and pd.notna(row["ef"]) else None,
            })

        # Compute summary
        persistent_count = sum(1 for wr in waypoint_results if wr["persistent"])
        total_waypoints = len(waypoint_results)
        rf_values = [wr["rf_net_w_m2"] for wr in waypoint_results if wr["rf_net_w_m2"] is not None]
        ef_values = [wr["ef_j_per_m"] for wr in waypoint_results if wr["ef_j_per_m"] is not None]

        summary = {
            "contrail_probability": persistent_count / total_waypoints if total_waypoints > 0 else 0.0,
            "total_energy_forcing_j": sum(ef_values) if ef_values else 0.0,
            "mean_rf_net_w_m2": float(np.mean(rf_values)) if rf_values else 0.0,
            "max_contrail_lifetime_hours": max(
                (wr["contrail_age_hours"] for wr in waypoint_results if wr["contrail_age_hours"] is not None),
                default=0.0,
            ),
        }

        return {
            "flight_id": flight_id,
            "waypoint_results": waypoint_results,
            "summary": summary,
            "used_fallback": False,
        }

    except Exception as e:
        logger.error(f"CoCiP model failed: {e}", exc_info=True)
        return None
