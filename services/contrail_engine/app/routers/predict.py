import logging
import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import settings
from app.models.requests import PredictRequest
from app.models.responses import ContrailSummary, PredictResponse, WaypointResult
from app.services.co2_service import calculate_co2_kg
from app.services.sac_fallback import predict_with_sac
from app.services.weather_service import get_weather_along_route

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/predict", response_model=PredictResponse)
async def predict_contrails(request: PredictRequest):
    """Predict contrail formation for a flight trajectory."""
    flight_id = request.flight_id or str(uuid.uuid4())[:8]
    waypoints_dict = [wp.model_dump() for wp in request.waypoints]

    # Extract date from first waypoint
    date = request.waypoints[0].time.strftime("%Y-%m-%d")

    # Try CoCiP first (unless fallback-only mode)
    used_fallback = True

    if not settings.fallback_only:
        try:
            from app.services.cocip_service import run_cocip

            cocip_result = await run_cocip(
                request.waypoints, request.aircraft_type, flight_id
            )
            if cocip_result is not None:
                # Calculate CO2
                co2 = calculate_co2_kg(
                    request.aircraft_type,
                    request.waypoints[0].latitude,
                    request.waypoints[0].longitude,
                    request.waypoints[-1].latitude,
                    request.waypoints[-1].longitude,
                )
                cocip_result["co2_kg"] = co2
                return PredictResponse(
                    flight_id=cocip_result["flight_id"],
                    waypoint_results=[
                        WaypointResult(**wr) for wr in cocip_result["waypoint_results"]
                    ],
                    summary=ContrailSummary(**cocip_result["summary"]),
                    co2_kg=co2,
                    used_fallback=False,
                )
        except Exception as e:
            logger.warning(f"CoCiP failed, falling back to SAC: {e}")

    # SAC fallback
    logger.info(f"Using SAC fallback for flight {flight_id}")
    weather_data = await get_weather_along_route(waypoints_dict, date)
    sac_results = predict_with_sac(waypoints_dict, weather_data)

    # Calculate CO2
    co2 = calculate_co2_kg(
        request.aircraft_type,
        request.waypoints[0].latitude,
        request.waypoints[0].longitude,
        request.waypoints[-1].latitude,
        request.waypoints[-1].longitude,
    )

    # Build summary from SAC results
    persistent_count = sum(1 for r in sac_results if r["persistent"])
    total = len(sac_results)
    rf_values = [r["rf_net_w_m2"] for r in sac_results if r["rf_net_w_m2"] is not None]

    summary = ContrailSummary(
        contrail_probability=persistent_count / total if total > 0 else 0.0,
        total_energy_forcing_j=0.0,  # Not available in SAC mode
        mean_rf_net_w_m2=sum(rf_values) / len(rf_values) if rf_values else 0.0,
        max_contrail_lifetime_hours=max(
            (r["contrail_age_hours"] for r in sac_results if r["contrail_age_hours"]),
            default=0.0,
        ),
    )

    return PredictResponse(
        flight_id=flight_id,
        waypoint_results=[WaypointResult(**r) for r in sac_results],
        summary=summary,
        co2_kg=co2,
        used_fallback=True,
    )
