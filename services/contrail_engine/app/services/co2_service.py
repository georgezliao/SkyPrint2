"""ICAO-based CO2 emissions calculator.

Uses polynomial fuel burn coefficients derived from the ICAO Carbon Emissions Calculator
methodology. CO2 = fuel_kg * 3.157 (1 kg Jet-A produces 3.157 kg CO2).
"""

from app.models.common import AircraftType
from app.utils.geo import great_circle_distance_km

# ICAO fuel coefficients: (seats, load_factor, a, b, c) where fuel_kg = a*d^2 + b*d + c
# Coefficients are approximate and cover short/medium/long-haul combined
AIRCRAFT_DATA: dict[str, dict] = {
    "B738": {"seats": 162, "a": 0.0, "b": 3.05, "c": 1550},
    "B739": {"seats": 178, "a": 0.0, "b": 3.15, "c": 1600},
    "B77W": {"seats": 396, "a": 0.0, "b": 8.90, "c": 3200},
    "B789": {"seats": 296, "a": 0.0, "b": 5.80, "c": 2400},
    "B78X": {"seats": 318, "a": 0.0, "b": 5.60, "c": 2300},
    "A320": {"seats": 150, "a": 0.0, "b": 2.90, "c": 1500},
    "A321": {"seats": 185, "a": 0.0, "b": 3.30, "c": 1700},
    "A332": {"seats": 247, "a": 0.0, "b": 6.30, "c": 2800},
    "A333": {"seats": 277, "a": 0.0, "b": 6.50, "c": 2900},
    "A359": {"seats": 325, "a": 0.0, "b": 5.70, "c": 2200},
    "A35K": {"seats": 366, "a": 0.0, "b": 6.00, "c": 2400},
    "E190": {"seats": 97, "a": 0.0, "b": 2.30, "c": 1100},
}

CO2_PER_KG_FUEL = 3.157
DEFAULT_LOAD_FACTOR = 0.82
PAX_TO_FREIGHT_RATIO = 0.951  # Passenger share of total payload


def calculate_co2_kg(
    aircraft_type: AircraftType,
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    load_factor: float = DEFAULT_LOAD_FACTOR,
) -> float:
    """Calculate per-passenger CO2 emissions in kg."""
    distance_km = great_circle_distance_km(origin_lat, origin_lon, dest_lat, dest_lon)
    aircraft = AIRCRAFT_DATA.get(aircraft_type.value)

    if not aircraft:
        # Fallback: use A320 as default
        aircraft = AIRCRAFT_DATA["A320"]

    a, b, c = aircraft["a"], aircraft["b"], aircraft["c"]
    seats = aircraft["seats"]

    # Total fuel burn (kg)
    total_fuel = a * distance_km**2 + b * distance_km + c

    # Per-passenger fuel
    fuel_per_pax = total_fuel / (seats * load_factor * PAX_TO_FREIGHT_RATIO)

    # CO2 per passenger
    return round(fuel_per_pax * CO2_PER_KG_FUEL, 2)
