"""Unit conversion utilities for aviation and atmospheric calculations."""

FEET_TO_METERS = 0.3048
METERS_TO_FEET = 3.28084


def feet_to_meters(feet: float) -> float:
    return feet * FEET_TO_METERS


def meters_to_feet(meters: float) -> float:
    return meters * METERS_TO_FEET


def pressure_to_altitude_ft(pressure_hpa: float) -> float:
    """Standard atmosphere pressure to altitude conversion."""
    altitude_m = 44330 * (1 - (pressure_hpa / 1013.25) ** 0.1903)
    return altitude_m * METERS_TO_FEET


def altitude_ft_to_pressure(altitude_ft: float) -> float:
    """Approximate altitude to pressure conversion (standard atmosphere)."""
    altitude_m = altitude_ft * FEET_TO_METERS
    return 1013.25 * (1 - altitude_m / 44330) ** 5.255


def celsius_to_kelvin(celsius: float) -> float:
    return celsius + 273.15


def kelvin_to_celsius(kelvin: float) -> float:
    return kelvin - 273.15
