from pydantic import BaseModel, Field

from app.models.common import AircraftType, Waypoint


class PredictRequest(BaseModel):
    waypoints: list[Waypoint] = Field(min_length=2)
    aircraft_type: AircraftType
    flight_id: str | None = None


class CompareRequest(BaseModel):
    trajectory_a: list[Waypoint] = Field(min_length=2)
    trajectory_b: list[Waypoint] = Field(min_length=2)
    aircraft_type: AircraftType


class OptimizeRequest(BaseModel):
    waypoints: list[Waypoint] = Field(min_length=2)
    aircraft_type: AircraftType
    altitude_range_ft: tuple[int, int] = (29000, 43000)
    step_ft: int = 1000


class RouteHistoryRequest(BaseModel):
    callsign: str = Field(min_length=3, max_length=10, description="Flight callsign, e.g. AAL100")
    icao24: str = Field(min_length=6, max_length=6, description="ICAO 24-bit transponder hex, e.g. a9b9e3")
    departure_time_unix: int = Field(description="Unix timestamp near the departure time")
    aircraft_type: AircraftType
