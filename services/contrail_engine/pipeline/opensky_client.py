"""OpenSky Network API client with OAuth2 authentication.

Handles token refresh, rate limiting, and the /tracks/all endpoint
quirk discovered during Phase 1 verification.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import requests as http_requests

logger = logging.getLogger(__name__)

TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network"
    "/protocol/openid-connect/token"
)
API_BASE = "https://opensky-network.org/api"

# Rate-limit: wait this many seconds between successive API calls
REQUEST_INTERVAL_S = 1.5


@dataclass
class FlightRecord:
    """A single flight record from the OpenSky /flights endpoint."""

    icao24: str
    callsign: str
    departure_airport: str | None
    arrival_airport: str | None
    first_seen: int  # unix timestamp
    last_seen: int

    @property
    def duration_h(self) -> float:
        return (self.last_seen - self.first_seen) / 3600.0

    @property
    def departure_utc(self) -> datetime:
        return datetime.fromtimestamp(self.first_seen, tz=timezone.utc)

    @property
    def arrival_utc(self) -> datetime:
        return datetime.fromtimestamp(self.last_seen, tz=timezone.utc)


@dataclass
class TrackPoint:
    """One waypoint from the /tracks/all response."""

    time: int  # unix timestamp
    latitude: float | None
    longitude: float | None
    baro_altitude_m: float | None
    heading: float | None
    on_ground: bool


@dataclass
class FlightTrack:
    """Full trajectory from OpenSky."""

    icao24: str
    callsign: str
    start_time: int
    end_time: int
    path: list[TrackPoint] = field(default_factory=list)


class OpenSkyClient:
    """Authenticated OpenSky REST client.

    Usage::

        client = OpenSkyClient(client_id="...", client_secret="...")
        departures = client.get_departures("KJFK", begin_ts, end_ts)
        track = client.get_track(icao24, time_ts)
    """

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token: str | None = None
        self._token_expires: float = 0.0
        self._last_request: float = 0.0

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _ensure_token(self) -> None:
        if self._access_token and time.time() < self._token_expires - 60:
            return
        resp = http_requests.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
            timeout=15,
        )
        resp.raise_for_status()
        body = resp.json()
        self._access_token = body["access_token"]
        self._token_expires = time.time() + body.get("expires_in", 300)
        logger.debug("OpenSky token refreshed")

    def _headers(self) -> dict[str, str]:
        self._ensure_token()
        return {"Authorization": f"Bearer {self._access_token}"}

    # ------------------------------------------------------------------
    # Throttle
    # ------------------------------------------------------------------

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request
        if elapsed < REQUEST_INTERVAL_S:
            time.sleep(REQUEST_INTERVAL_S - elapsed)
        self._last_request = time.time()

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    def get_departures(
        self, airport_icao: str, begin: int, end: int
    ) -> list[FlightRecord]:
        """Fetch departures from *airport_icao* between *begin* and *end* (unix)."""
        self._throttle()
        url = f"{API_BASE}/flights/departure"
        resp = http_requests.get(
            url,
            params={"airport": airport_icao, "begin": begin, "end": end},
            headers=self._headers(),
            timeout=30,
        )
        if resp.status_code == 429:
            logger.warning("OpenSky rate limited on departures")
            return []
        resp.raise_for_status()
        return [
            FlightRecord(
                icao24=f.get("icao24", ""),
                callsign=(f.get("callsign") or "").strip(),
                departure_airport=f.get("estDepartureAirport"),
                arrival_airport=f.get("estArrivalAirport"),
                first_seen=f.get("firstSeen", 0),
                last_seen=f.get("lastSeen", 0),
            )
            for f in resp.json()
        ]

    def get_arrivals(
        self, airport_icao: str, begin: int, end: int
    ) -> list[FlightRecord]:
        """Fetch arrivals at *airport_icao* between *begin* and *end* (unix)."""
        self._throttle()
        url = f"{API_BASE}/flights/arrival"
        resp = http_requests.get(
            url,
            params={"airport": airport_icao, "begin": begin, "end": end},
            headers=self._headers(),
            timeout=30,
        )
        if resp.status_code == 429:
            logger.warning("OpenSky rate limited on arrivals")
            return []
        resp.raise_for_status()
        return [
            FlightRecord(
                icao24=f.get("icao24", ""),
                callsign=(f.get("callsign") or "").strip(),
                departure_airport=f.get("estDepartureAirport"),
                arrival_airport=f.get("estArrivalAirport"),
                first_seen=f.get("firstSeen", 0),
                last_seen=f.get("lastSeen", 0),
            )
            for f in resp.json()
        ]

    def get_track(self, icao24: str, time_unix: int) -> FlightTrack | None:
        """Fetch a flight track via ``/tracks/all``.

        The correct endpoint is ``/tracks/all`` (NOT ``/tracks``).
        Verified during Phase 1: ``/tracks`` returns 404.

        Returns *None* on 404 (track unavailable) or 429 (rate limited).
        """
        self._throttle()
        url = f"{API_BASE}/tracks/all"
        resp = http_requests.get(
            url,
            params={"icao24": icao24, "time": time_unix},
            headers=self._headers(),
            timeout=30,
        )
        if resp.status_code in (404, 429):
            if resp.status_code == 429:
                logger.warning("OpenSky rate limited on tracks")
            return None
        resp.raise_for_status()

        data = resp.json()
        path_raw = data.get("path", [])
        path = [
            TrackPoint(
                time=wp[0],
                latitude=wp[1],
                longitude=wp[2],
                baro_altitude_m=wp[3],
                heading=wp[4],
                on_ground=wp[5],
            )
            for wp in path_raw
        ]

        return FlightTrack(
            icao24=data.get("icao24", icao24),
            callsign=(data.get("callsign") or "").strip(),
            start_time=int(data.get("startTime", 0)),
            end_time=int(data.get("endTime", 0)),
            path=path,
        )
