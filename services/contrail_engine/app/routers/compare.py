import logging
import uuid

from fastapi import APIRouter

from app.models.requests import CompareRequest, PredictRequest
from app.models.responses import CompareResponse
from app.routers.predict import predict_contrails

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/compare", response_model=CompareResponse)
async def compare_trajectories(request: CompareRequest):
    """Compare two flight trajectories for contrail impact."""
    # Run prediction for both trajectories
    result_a = await predict_contrails(
        PredictRequest(
            waypoints=request.trajectory_a,
            aircraft_type=request.aircraft_type,
            flight_id=f"cmp-a-{uuid.uuid4().hex[:6]}",
        )
    )

    result_b = await predict_contrails(
        PredictRequest(
            waypoints=request.trajectory_b,
            aircraft_type=request.aircraft_type,
            flight_id=f"cmp-b-{uuid.uuid4().hex[:6]}",
        )
    )

    # Calculate deltas
    ef_a = result_a.summary.total_energy_forcing_j
    ef_b = result_b.summary.total_energy_forcing_j
    delta_ef = ((ef_b - ef_a) / ef_a * 100) if ef_a != 0 else 0.0

    co2_a = result_a.co2_kg
    co2_b = result_b.co2_kg
    delta_co2 = ((co2_b - co2_a) / co2_a * 100) if co2_a != 0 else 0.0

    # Generate recommendation
    impact_a = result_a.summary.contrail_probability * 100 + co2_a
    impact_b = result_b.summary.contrail_probability * 100 + co2_b

    if impact_a < impact_b:
        recommendation = "Trajectory A has lower total climate impact."
    elif impact_b < impact_a:
        recommendation = "Trajectory B has lower total climate impact."
    else:
        recommendation = "Both trajectories have similar climate impact."

    return CompareResponse(
        trajectory_a=result_a,
        trajectory_b=result_b,
        delta_ef_percent=round(delta_ef, 2),
        delta_co2_percent=round(delta_co2, 2),
        recommendation=recommendation,
    )
