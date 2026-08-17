"""Altitude optimization to minimize contrail formation.

Uses SAC-based screening across altitude candidates, then selects
the profile that avoids contrail formation while staying closest
to the original cruise altitude.
"""

import logging

from app.models.common import Waypoint
from app.services.sac_fallback import check_persistence, check_sac
from app.services.weather_service import WeatherPoint
from app.utils.conversions import altitude_ft_to_pressure

logger = logging.getLogger(__name__)


def optimize_altitude_profile(
    waypoints: list[dict],
    weather_data: list[list[WeatherPoint]],
    altitude_range: tuple[int, int] = (29000, 43000),
    step: int = 1000,
) -> list[dict]:
    """Find optimal altitude for each waypoint to minimize contrail formation.

    For each waypoint, searches the altitude range for the altitude closest
    to the original that avoids SAC satisfaction. If no contrail-free altitude
    exists, keeps the original.

    Returns list of altitude adjustments.
    """
    adjustments = []

    for i, wp in enumerate(waypoints):
        original_alt = wp["altitude_ft"]

        # Skip climb/descent phases (below 25000 ft)
        if original_alt < 25000:
            continue

        weather_idx = min(i, len(weather_data) - 1)
        weather_layers = weather_data[weather_idx] if weather_data else []

        if not weather_layers:
            continue

        # Check if contrail forms at original altitude
        orig_pressure = altitude_ft_to_pressure(original_alt)
        orig_layer = _find_closest_layer(weather_layers, orig_pressure)

        if orig_layer is None:
            continue

        orig_sac = check_sac(orig_layer.temperature_c, orig_layer.relative_humidity, orig_pressure)
        orig_persistent = orig_sac and check_persistence(
            orig_layer.temperature_c, orig_layer.relative_humidity
        )

        if not orig_persistent:
            # No persistent contrail at original altitude, no adjustment needed
            continue

        # Search for contrail-free altitude
        best_alt = None
        best_distance = float("inf")

        for alt in range(altitude_range[0], altitude_range[1] + 1, step):
            pressure = altitude_ft_to_pressure(alt)
            layer = _find_closest_layer(weather_layers, pressure)

            if layer is None:
                continue

            sac = check_sac(layer.temperature_c, layer.relative_humidity, pressure)
            persistent = sac and check_persistence(layer.temperature_c, layer.relative_humidity)

            if not persistent:
                distance = abs(alt - original_alt)
                if distance < best_distance:
                    best_distance = distance
                    best_alt = alt

        if best_alt is not None and best_alt != original_alt:
            direction = "higher" if best_alt > original_alt else "lower"
            diff = abs(best_alt - original_alt)
            adjustments.append({
                "waypoint_index": i,
                "original_altitude_ft": original_alt,
                "suggested_altitude_ft": best_alt,
                "reason": f"Move {diff}ft {direction} to avoid persistent contrail formation",
            })

    return adjustments


def _find_closest_layer(
    layers: list[WeatherPoint], target_pressure: float
) -> WeatherPoint | None:
    """Find the weather layer closest to the target pressure level."""
    if not layers:
        return None

    return min(layers, key=lambda l: abs(l.pressure_hpa - target_pressure))
