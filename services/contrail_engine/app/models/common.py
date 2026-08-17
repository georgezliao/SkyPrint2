from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Waypoint(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    altitude_ft: float = Field(gt=0, description="Altitude in feet")
    time: datetime = Field(description="UTC timestamp")


class AircraftType(str, Enum):
    B738 = "B738"
    B739 = "B739"
    B77W = "B77W"
    B789 = "B789"
    B78X = "B78X"
    A320 = "A320"
    A321 = "A321"
    A332 = "A332"
    A333 = "A333"
    A359 = "A359"
    A35K = "A35K"
    E190 = "E190"
