"""Historical flight route geometry endpoint.

Fetches an OpenSky ADS-B track and returns:
- The actual flown path (lat/lon/altitude waypoints)
- The contrail-optimal path (same lat/lon, cruise altitudes shifted by the SAC
  optimiser to avoid persistent contrail formation)
- Per-passenger CO2 before and after the altitude adjustment
- Estimated energy-forcing reduction (SAC-based, not full CoCiP)

CoCiP / ERA5 are intentionally not used here because ERA5 is unavailable on
demand for arbitrary historical dates. Use the batch pipeline for ERA5 analysis.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.models.common import AircraftType, Waypoint
from app.models.requests import RouteHistoryRequest
from app.models.responses import RouteGeometryPoint, RouteHistoryResponse
from app.services.co2_service import calculate_co2_kg
from app.services.optimizer import optimize_altitude_profile
from app.services.weather_service import get_weather_along_route
from pipeline.route_geometry import build_route_geometry

logger = logging.getLogger(__name__)

router = APIRouter()


def _track_to_waypoints(path: list) -> list[Waypoint]:
    """Convert OpenSky TrackPoints to app Waypoints, dropping ground/null points."""
    waypoints = []
    for pt in path:
        if pt.on_ground:
            continue
        if pt.latitude is None or pt.longitude is None:
            continue
        if pt.baro_altitude_m is None or pt.baro_altitude_m < 300:
            continue
        waypoints.append(Waypoint(
            latitude=pt.latitude,
            longitude=pt.longitude,
            altitude_ft=pt.baro_altitude_m * 3.28084,
            time=datetime.fromtimestamp(pt.time, tz=timezone.utc),
        ))
    return waypoints


@router.post("/route-history", response_model=RouteHistoryResponse)
async def get_route_history(request: RouteHistoryRequest):
    """Return contrail-optimal route geometry for a historical OpenSky flight.

    The optimal path keeps the same lat/lon trajectory; only cruise altitudes
    are shifted to avoid persistent contrails within the 2 % fuel constraint
    (Teoh et al. 2020).
    """
    from pipeline.opensky_client import OpenSkyClient

    client_id = os.environ.get("OPENSKY_CLIENT_ID", "")
    client_secret = os.environ.get("OPENSKY_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="OpenSky credentials not configured")

    client = OpenSkyClient(client_id, client_secret)

    # OpenSky client is synchronous — run in a thread to avoid blocking the loop
    track = await asyncio.to_thread(
        client.get_track, request.icao24, request.departure_time_unix
    )
    if track is None:
        raise HTTPException(
            status_code=404,
            detail=f"No track found for {request.callsign}/{request.icao24} "
                   f"at t={request.departure_time_unix}. "
                   "OpenSky retains tracks for ~30 days; rate limits may also apply.",
        )

    waypoints = _track_to_waypoints(track.path)
    if len(waypoints) < 5:
        raise HTTPException(
            status_code=422,
            detail=f"Track has only {len(waypoints)} valid airborne points (minimum 5).",
        )

    # Build dicts with ISO-string times for weather service compatibility
    waypoints_dict = [
        {
            "latitude": wp.latitude,
            "longitude": wp.longitude,
            "altitude_ft": wp.altitude_ft,
            "time": wp.time.isoformat(),
        }
        for wp in waypoints
    ]
    date = waypoints[0].time.strftime("%Y-%m-%d")
    weather_data = await get_weather_along_route(waypoints_dict, date)

    # SAC-based altitude optimisation
    adjustments = optimize_altitude_profile(waypoints_dict, weather_data)

    # Apply adjustments and track which waypoints had contrails
    optimal_waypoints = list(waypoints)
    contrail_flags = [False] * len(waypoints)
    for adj in adjustments:
        idx = adj["waypoint_index"]
        contrail_flags[idx] = True
        if idx < len(optimal_waypoints):
            optimal_waypoints[idx] = optimal_waypoints[idx].model_copy(
                update={"altitude_ft": adj["suggested_altitude_ft"]}
            )

    # Per-passenger CO2 via ICAO polynomial method (great-circle distance)
    first, last = waypoints[0], waypoints[-1]
    co2_original = calculate_co2_kg(
        request.aircraft_type,
        first.latitude, first.longitude,
        last.latitude, last.longitude,
    )

    result = build_route_geometry(
        original_waypoints=waypoints,
        optimal_waypoints=optimal_waypoints,
        adjustments=adjustments,
        contrail_flags=contrail_flags,
        aircraft_type_str=request.aircraft_type.value,
        callsign=request.callsign,
        icao24=request.icao24,
        co2_original=co2_original,
    )

    return RouteHistoryResponse(
        flight_id=result.flight_id,
        callsign=result.callsign,
        icao24=result.icao24,
        aircraft_type=result.aircraft_type,
        original_path=[
            RouteGeometryPoint(
                time_unix=wp.time_unix,
                latitude=wp.latitude,
                longitude=wp.longitude,
                altitude_ft=wp.altitude_ft,
                contrail_risk=wp.contrail_risk,
            )
            for wp in result.original_path
        ],
        optimal_path=[
            RouteGeometryPoint(
                time_unix=wp.time_unix,
                latitude=wp.latitude,
                longitude=wp.longitude,
                altitude_ft=wp.altitude_ft,
                contrail_risk=wp.contrail_risk,
            )
            for wp in result.optimal_path
        ],
        co2_kg_original=result.co2_kg_original,
        co2_kg_optimal=result.co2_kg_optimal,
        co2_kg_delta=result.co2_kg_delta,
        n_contrail_waypoints=result.n_contrail_waypoints,
        n_total_waypoints=result.n_total_waypoints,
        fuel_penalty_pct=result.fuel_penalty_pct,
        ef_reduction_pct=result.ef_reduction_pct,
        avoidable=result.avoidable,
        used_sac_fallback=True,
        altitude_adjustments=adjustments,
    )
