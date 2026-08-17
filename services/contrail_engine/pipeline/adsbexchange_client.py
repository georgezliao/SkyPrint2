"""ADS-B Exchange free trace file client.

ADS-B Exchange publishes full-history trace files for the 1st of every month
at no cost. Files are served gzip-compressed (handled transparently by requests).

URL pattern:
    https://samples.adsbexchange.com/traces/{yyyy}/{mm}/{dd}/{icao24[-2:]}/trace_full_{icao24}.json

Trace array columns (0-indexed):
    0  relative_time_s   float — seconds since base `timestamp`
    1  latitude          float
    2  longitude         float
    3  alt_baro          int|str — feet ("ground" when on-ground)
    4  ground_speed_kts  float|None
    5  track_deg         float|None
    6  flags             int — bit 0: on_ground, bit 1: stale/interpolated
    7+ additional fields (ignored)

Returned object is a pipeline.opensky_client.FlightTrack so it can be
passed directly to opensky_track_to_flight().
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

from pipeline.opensky_client import FlightTrack, TrackPoint

logger = logging.getLogger(__name__)

BASE_URL = "https://samples.adsbexchange.com/traces"
_FEET_TO_METERS = 0.3048


def _is_first_of_month(unix_ts: int) -> bool:
    """Return True if *unix_ts* falls on the 1st day of its UTC month."""
    dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    return dt.day == 1


def fetch_trace(icao24: str, date_unix: int) -> FlightTrack | None:
    """Fetch an ADS-B Exchange trace for *icao24* on the date of *date_unix*.

    Returns None if the file is not available (HTTP 404 or non-1st-of-month).
    Only free for the 1st of each month; caller should verify with
    _is_first_of_month() before calling.
    """
    dt = datetime.fromtimestamp(date_unix, tz=timezone.utc)
    yyyy = dt.strftime("%Y")
    mm = dt.strftime("%m")
    dd = dt.strftime("%d")
    icao_lower = icao24.lower()
    suffix = icao_lower[-2:]  # last two hex chars for directory sharding

    url = f"{BASE_URL}/{yyyy}/{mm}/{dd}/{suffix}/trace_full_{icao_lower}.json"
    logger.debug("ADS-B Exchange fetch: %s", url)

    try:
        resp = requests.get(
            url,
            timeout=30,
            headers={"Accept-Encoding": "gzip, deflate"},
        )
    except requests.RequestException as exc:
        logger.warning("ADS-B Exchange request failed for %s: %s", icao24, exc)
        return None

    if resp.status_code == 404:
        logger.debug("ADS-B Exchange: no trace for %s on %s-%s-%s", icao24, yyyy, mm, dd)
        return None

    if not resp.ok:
        logger.warning(
            "ADS-B Exchange returned HTTP %d for %s", resp.status_code, icao24
        )
        return None

    try:
        data = resp.json()
    except Exception as exc:
        logger.warning("ADS-B Exchange JSON parse failed for %s: %s", icao24, exc)
        return None

    return _parse_trace(data, icao24)


def _parse_trace(data: dict, icao24: str) -> FlightTrack | None:
    """Convert raw ADS-B Exchange trace JSON to a FlightTrack."""
    base_ts: float = data.get("timestamp", 0.0)
    raw_trace: list = data.get("trace", [])

    if not raw_trace:
        logger.debug("ADS-B Exchange: empty trace for %s", icao24)
        return None

    path: list[TrackPoint] = []
    for row in raw_trace:
        if len(row) < 4:
            continue

        rel_time = row[0]
        lat = row[1]
        lon = row[2]
        alt_raw = row[3]
        flags = int(row[6]) if len(row) > 6 and row[6] is not None else 0
        heading = row[5] if len(row) > 5 and row[5] is not None else None

        # Skip rows with missing position
        if lat is None or lon is None:
            continue

        on_ground = bool(flags & 1) or (isinstance(alt_raw, str) and alt_raw == "ground")

        if isinstance(alt_raw, (int, float)):
            baro_altitude_m = float(alt_raw) * _FEET_TO_METERS
        else:
            baro_altitude_m = None

        abs_time = int(base_ts + rel_time)

        path.append(TrackPoint(
            time=abs_time,
            latitude=float(lat),
            longitude=float(lon),
            baro_altitude_m=baro_altitude_m,
            heading=float(heading) if heading is not None else None,
            on_ground=on_ground,
        ))

    if not path:
        return None

    callsign = (data.get("r") or icao24).strip()
    start_time = path[0].time
    end_time = path[-1].time

    logger.info(
        "ADS-B Exchange: %s — %d points, %s → %s",
        icao24, len(path),
        datetime.fromtimestamp(start_time, tz=timezone.utc).isoformat(),
        datetime.fromtimestamp(end_time, tz=timezone.utc).isoformat(),
    )

    return FlightTrack(
        icao24=icao24.lower(),
        callsign=callsign,
        start_time=start_time,
        end_time=end_time,
        path=path,
    )
