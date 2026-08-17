"""Weather data fetching and caching for contrail prediction.

Supports two modes:
1. Open-Meteo API — point queries for SAC fallback (lightweight)
2. PyContrails GFSForecast — gridded data for full CoCiP model (heavyweight)
"""

import logging
from datetime import datetime

import httpx
from cachetools import TTLCache

from app.config import settings

logger = logging.getLogger(__name__)

# In-memory cache: key = (rounded_lat, rounded_lon, pressure_hpa, hour)
# TTL = 3 hours (GFS updates every 6 hours)
_weather_cache: TTLCache = TTLCache(maxsize=10000, ttl=3 * 3600)

PRESSURE_LEVELS = [150, 200, 250, 300, 350]


class WeatherPoint:
    """Atmospheric conditions at a specific point and pressure level."""

    def __init__(
        self,
        latitude: float,
        longitude: float,
        pressure_hpa: int,
        temperature_c: float,
        relative_humidity: float,
        time: str,
    ):
        self.latitude = latitude
        self.longitude = longitude
        self.pressure_hpa = pressure_hpa
        self.temperature_c = temperature_c
        self.relative_humidity = relative_humidity
        self.time = time


async def get_weather_at_point(
    latitude: float,
    longitude: float,
    date: str,
    hour: int = 12,
) -> list[WeatherPoint]:
    """Fetch weather data at a point for all cruise pressure levels via Open-Meteo."""
    # Round coords to 0.25° grid for cache key normalization
    rlat = round(latitude * 4) / 4
    rlon = round(longitude * 4) / 4

    cache_key = (rlat, rlon, date, hour)
    if cache_key in _weather_cache:
        return _weather_cache[cache_key]

    pressure_vars = []
    for p in PRESSURE_LEVELS:
        pressure_vars.extend([f"temperature_{p}hPa", f"relative_humidity_{p}hPa"])

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(pressure_vars),
        "start_date": date,
        "end_date": date,
        "timezone": "UTC",
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(settings.open_meteo_base_url, params=params)
        response.raise_for_status()
        data = response.json()

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])

    # Find the closest hour index
    target_idx = min(hour, len(times) - 1) if times else 0

    results = []
    for p in PRESSURE_LEVELS:
        temp_key = f"temperature_{p}hPa"
        rh_key = f"relative_humidity_{p}hPa"

        temp = hourly.get(temp_key, [None])[target_idx]
        rh = hourly.get(rh_key, [None])[target_idx]

        if temp is not None and rh is not None:
            results.append(
                WeatherPoint(
                    latitude=latitude,
                    longitude=longitude,
                    pressure_hpa=p,
                    temperature_c=temp,
                    relative_humidity=rh,
                    time=times[target_idx] if times else date,
                )
            )

    _weather_cache[cache_key] = results
    return results


async def get_weather_along_route(
    waypoints: list[dict],
    date: str,
) -> list[list[WeatherPoint]]:
    """Fetch weather for multiple waypoints along a route."""
    # Sample waypoints (max 10 to limit API calls)
    sample_count = min(len(waypoints), 10)
    step = max(1, len(waypoints) // sample_count)
    sampled = [waypoints[i] for i in range(0, len(waypoints), step)][:sample_count]

    results = []
    for wp in sampled:
        hour = datetime.fromisoformat(wp["time"].replace("Z", "+00:00")).hour if "time" in wp else 12
        weather = await get_weather_at_point(wp["latitude"], wp["longitude"], date, hour)
        results.append(weather)

    return results
