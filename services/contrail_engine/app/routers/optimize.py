import logging
import uuid

from fastapi import APIRouter

from app.models.requests import OptimizeRequest, PredictRequest
from app.models.responses import AltitudeAdjustment, OptimizeResponse
from app.routers.predict import predict_contrails
from app.services.optimizer import optimize_altitude_profile
from app.services.weather_service import get_weather_along_route

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/optimize", response_model=OptimizeResponse)
async def optimize_altitude(request: OptimizeRequest):
    """Suggest optimal altitude to minimize contrail formation."""
    waypoints_dict = [wp.model_dump() for wp in request.waypoints]
    date = request.waypoints[0].time.strftime("%Y-%m-%d")

    # Get weather data
    weather_data = await get_weather_along_route(waypoints_dict, date)

    # Run optimizer to find better altitudes
    adjustments = optimize_altitude_profile(
        waypoints_dict,
        weather_data,
        altitude_range=request.altitude_range_ft,
        step=request.step_ft,
    )

    # Predict original trajectory
    original = await predict_contrails(
        PredictRequest(
            waypoints=request.waypoints,
            aircraft_type=request.aircraft_type,
            flight_id=f"opt-orig-{uuid.uuid4().hex[:6]}",
        )
    )

    # Apply altitude adjustments and predict optimized trajectory
    optimized_waypoints = list(request.waypoints)
    for adj in adjustments:
        idx = adj["waypoint_index"]
        if idx < len(optimized_waypoints):
            optimized_waypoints[idx] = optimized_waypoints[idx].model_copy(
                update={"altitude_ft": adj["suggested_altitude_ft"]}
            )

    optimized = await predict_contrails(
        PredictRequest(
            waypoints=optimized_waypoints,
            aircraft_type=request.aircraft_type,
            flight_id=f"opt-new-{uuid.uuid4().hex[:6]}",
        )
    )

    # Calculate reduction
    orig_ef = original.summary.total_energy_forcing_j
    opt_ef = optimized.summary.total_energy_forcing_j
    ef_reduction = ((orig_ef - opt_ef) / orig_ef * 100) if orig_ef != 0 else 0.0

    return OptimizeResponse(
        original=original,
        optimized=optimized,
        altitude_adjustments=[AltitudeAdjustment(**a) for a in adjustments],
        ef_reduction_percent=round(ef_reduction, 2),
    )
