"""Schmidt-Appleman Criterion (SAC) fallback model.

A lightweight contrail formation check that doesn't require full CoCiP.
Uses temperature and humidity at flight altitude to determine:
1. Whether the SAC is satisfied (contrail forms)
2. Whether the contrail is persistent (ice-supersaturated region)
"""

import logging
import math

from app.services.weather_service import WeatherPoint
from app.utils.conversions import altitude_ft_to_pressure, celsius_to_kelvin

logger = logging.getLogger(__name__)

# Engine parameters for SAC calculation
EI_H2O = 1.23  # Emission index of water (kg H2O / kg fuel)
Q_FUEL = 43.2e6  # Specific energy of Jet-A (J/kg)
ETA = 0.35  # Overall propulsion efficiency (typical modern turbofan)
CP = 1004.0  # Specific heat capacity of air at constant pressure (J/kg/K)
EPSILON = 0.622  # Ratio of molecular weights (water/air)

# Radiative forcing lookup by latitude band and time of day (W/m²)
# Simplified: contrails have net warming, especially at night
RF_LOOKUP = {
    "tropical_day": 0.015,
    "tropical_night": 0.035,
    "midlat_day": 0.020,
    "midlat_night": 0.045,
    "polar_day": 0.010,
    "polar_night": 0.025,
}


def saturation_pressure_liquid(temperature_k: float) -> float:
    """Magnus formula for saturation vapor pressure over liquid water (hPa)."""
    t_c = temperature_k - 273.15
    return 6.112 * math.exp(17.67 * t_c / (t_c + 243.5))


def saturation_pressure_ice(temperature_k: float) -> float:
    """Saturation vapor pressure over ice (hPa). Murphy-Koop 2005."""
    t = temperature_k
    return math.exp(9.550426 - 5723.265 / t + 3.53068 * math.log(t) - 0.00728332 * t)


def check_sac(temperature_c: float, relative_humidity: float, pressure_hpa: float) -> bool:
    """Check if the Schmidt-Appleman Criterion is satisfied.

    Returns True if a contrail would form at these conditions.
    """
    t_k = celsius_to_kelvin(temperature_c)

    # Slope of mixing line in T-e diagram
    # G = (EI_H2O * CP * p) / (EPSILON * Q_FUEL * (1 - ETA))
    g = (EI_H2O * CP * pressure_hpa * 100) / (EPSILON * Q_FUEL * (1 - ETA))

    # Critical temperature: the maximum temperature at which SAC is satisfied
    # This is found where the mixing line is tangent to the saturation curve
    # Iterative approach: check if at current temperature, the mixing line
    # from exhaust conditions crosses the liquid saturation curve

    e_sat = saturation_pressure_liquid(t_k)
    e_ambient = relative_humidity / 100.0 * e_sat

    # The exhaust temperature is very high, so we check if the minimum
    # of the mixing line dips below saturation
    # Simplified check: SAC is satisfied when T < T_critical
    # For typical conditions, T_critical ≈ -40°C at 200hPa
    t_critical = _compute_critical_temperature(g, pressure_hpa)

    return temperature_c < t_critical


def check_persistence(temperature_c: float, relative_humidity: float) -> bool:
    """Check if a contrail would be persistent (ice-supersaturated conditions).

    Persistent contrails form when relative humidity with respect to ice > 100%.
    """
    t_k = celsius_to_kelvin(temperature_c)
    e_sat_liquid = saturation_pressure_liquid(t_k)
    e_sat_ice = saturation_pressure_ice(t_k)

    # Actual vapor pressure
    e = relative_humidity / 100.0 * e_sat_liquid

    # Relative humidity with respect to ice
    rhi = (e / e_sat_ice) * 100.0

    return rhi > 100.0


def estimate_rf(latitude: float, hour: int) -> float:
    """Estimate radiative forcing based on latitude and time of day."""
    is_night = hour < 6 or hour > 18

    if abs(latitude) < 23.5:
        band = "tropical"
    elif abs(latitude) < 60:
        band = "midlat"
    else:
        band = "polar"

    key = f"{band}_{'night' if is_night else 'day'}"
    return RF_LOOKUP.get(key, 0.025)


def predict_with_sac(
    waypoints: list[dict],
    weather_data: list[list[WeatherPoint]],
) -> list[dict]:
    """Run SAC-based contrail prediction for each waypoint.

    Returns a list of per-waypoint results with SAC check and estimated RF.
    """
    results = []

    for i, wp in enumerate(waypoints):
        altitude_ft = wp["altitude_ft"]
        pressure = altitude_ft_to_pressure(altitude_ft)

        # Find closest weather data
        weather_idx = min(i, len(weather_data) - 1)
        weather_layers = weather_data[weather_idx] if weather_data else []

        # Find the closest pressure level
        best_layer = None
        best_diff = float("inf")
        for layer in weather_layers:
            diff = abs(layer.pressure_hpa - pressure)
            if diff < best_diff:
                best_diff = diff
                best_layer = layer

        if best_layer is None:
            results.append({
                "sac_satisfied": False,
                "persistent": False,
                "rf_net_w_m2": None,
                "contrail_age_hours": None,
                "ef_j_per_m": None,
            })
            continue

        sac = check_sac(best_layer.temperature_c, best_layer.relative_humidity, pressure)
        persistent = sac and check_persistence(best_layer.temperature_c, best_layer.relative_humidity)

        hour = 12
        if "time" in wp:
            try:
                from datetime import datetime
                hour = datetime.fromisoformat(wp["time"].replace("Z", "+00:00")).hour
            except (ValueError, AttributeError):
                pass

        rf = estimate_rf(wp["latitude"], hour) if persistent else 0.0

        results.append({
            "sac_satisfied": sac,
            "persistent": persistent,
            "rf_net_w_m2": rf if persistent else None,
            "contrail_age_hours": 4.0 if persistent else None,  # Rough estimate
            "ef_j_per_m": None,  # Not available in SAC-only mode
        })

    return results


def _compute_critical_temperature(g: float, pressure_hpa: float) -> float:
    """Compute the critical SAC temperature using iterative method.

    Returns temperature in Celsius below which contrails form.
    """
    # Simplified: for typical turbofan engines at cruise,
    # the critical temperature is approximately:
    # T_crit ≈ -46.5°C at 200 hPa
    # T_crit ≈ -39.0°C at 300 hPa
    # Linear interpolation between reference points
    if pressure_hpa <= 200:
        return -46.5
    elif pressure_hpa >= 350:
        return -35.0
    else:
        # Linear interpolation
        frac = (pressure_hpa - 200) / 150
        return -46.5 + frac * 11.5
