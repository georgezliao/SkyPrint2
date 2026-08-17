"""Build a flight manifest for the NAT corridor retrospective window.

Queries OpenSky departures from major NAT departure airports, filters for
target airlines and European arrivals, and deduplicates to produce a manifest
of ~100 flights for CoCiP analysis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pipeline.opensky_client import FlightRecord, OpenSkyClient

logger = logging.getLogger(__name__)

# ICAO codes for major NAT departure/arrival airports
NAT_DEPARTURE_AIRPORTS = ["KJFK", "KORD", "KBOS", "KEWR", "KIAD", "KATL"]
NAT_EUROPEAN_AIRPORTS = [
    "EGLL", "LFPG", "EHAM", "EDDF", "EIDW", "LEMD",
    "LSZH", "EGCC", "LIRF", "LEBL", "EKCH", "ESSA",
    "ENGM", "LPPT",
]

# OpenSky /flights/departure max interval = 2 hours (7200s)
MAX_INTERVAL_S = 7200

# Minimum flight duration for transatlantic [hours]
MIN_DURATION_H = 4.5
MAX_DURATION_H = 12.0


@dataclass
class ManifestEntry:
    """One flight in the pipeline manifest."""

    icao24: str
    callsign: str
    airline_icao: str  # first 3 chars of callsign
    departure_airport: str
    arrival_airport: str
    first_seen: int
    last_seen: int
    aircraft_type: str | None = None  # filled later from ADS-B or external DB

    @property
    def flight_id(self) -> str:
        return f"{self.callsign}_{self.first_seen}"


@dataclass
class FlightManifest:
    """Complete manifest for the retrospective window."""

    entries: list[ManifestEntry] = field(default_factory=list)
    hero_flight: ManifestEntry | None = None
    window_start: str = ""
    window_end: str = ""
    query_airports: list[str] = field(default_factory=list)

    @property
    def airline_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self.entries:
            counts[e.airline_icao] = counts.get(e.airline_icao, 0) + 1
        return counts

    def summary(self) -> str:
        lines = [
            f"Manifest: {len(self.entries)} flights, "
            f"{len(self.airline_counts)} airlines",
            f"Window: {self.window_start} → {self.window_end}",
        ]
        for code, count in sorted(
            self.airline_counts.items(), key=lambda x: -x[1]
        ):
            lines.append(f"  {code}: {count}")
        if self.hero_flight:
            lines.append(
                f"Hero: {self.hero_flight.callsign} "
                f"({self.hero_flight.departure_airport}→"
                f"{self.hero_flight.arrival_airport})"
            )
        return "\n".join(lines)


def _callsign_to_airline(callsign: str) -> str | None:
    """Extract 3-letter ICAO airline code from callsign."""
    if not callsign or len(callsign) < 3:
        return None
    prefix = callsign[:3].upper()
    # Only alphabetic prefixes are ICAO codes
    if prefix.isalpha():
        return prefix
    return None


def _is_valid_transatlantic(
    rec: FlightRecord,
    target_airlines: dict[str, str],
    european_airports: set[str],
) -> bool:
    """Check if a flight record is a valid transatlantic target."""
    airline = _callsign_to_airline(rec.callsign)
    if airline not in target_airlines:
        return False
    if rec.arrival_airport not in european_airports:
        return False
    duration = rec.duration_h
    if duration < MIN_DURATION_H or duration > MAX_DURATION_H:
        return False
    return True


def build_manifest(
    client: OpenSkyClient,
    target_airlines: dict[str, str],
    window_start_utc: str,
    window_end_utc: str,
    departure_airports: list[str] | None = None,
    hero_callsign: str = "AAL100",
    max_flights: int = 150,
) -> FlightManifest:
    """Query OpenSky and build a filtered flight manifest.

    Parameters
    ----------
    client : OpenSkyClient
        Authenticated OpenSky client.
    target_airlines : dict
        ICAO code → airline name mapping.
    window_start_utc, window_end_utc : str
        ISO 8601 timestamps for the retrospective window.
    departure_airports : list, optional
        ICAO airport codes to query. Defaults to NAT_DEPARTURE_AIRPORTS.
    hero_callsign : str
        Callsign of the hero flight to flag separately.
    max_flights : int
        Cap on total manifest entries.

    Returns
    -------
    FlightManifest
    """
    if departure_airports is None:
        departure_airports = NAT_DEPARTURE_AIRPORTS

    start_dt = datetime.fromisoformat(window_start_utc.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(window_end_utc.replace("Z", "+00:00"))
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    european_set = set(NAT_EUROPEAN_AIRPORTS)
    seen_keys: set[str] = set()
    entries: list[ManifestEntry] = []
    hero: ManifestEntry | None = None

    for airport in departure_airports:
        logger.info("Querying departures from %s", airport)
        # Walk the window in 2-hour chunks (OpenSky API limit)
        chunk_start = start_ts
        while chunk_start < end_ts:
            chunk_end = min(chunk_start + MAX_INTERVAL_S, end_ts)
            try:
                records = client.get_departures(airport, chunk_start, chunk_end)
            except Exception:
                logger.exception(
                    "Failed to query %s [%s, %s]", airport, chunk_start, chunk_end
                )
                chunk_start = chunk_end
                continue

            for rec in records:
                if not _is_valid_transatlantic(rec, target_airlines, european_set):
                    continue

                # Deduplicate by icao24 + firstSeen
                key = f"{rec.icao24}_{rec.first_seen}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                airline = _callsign_to_airline(rec.callsign)
                entry = ManifestEntry(
                    icao24=rec.icao24,
                    callsign=rec.callsign,
                    airline_icao=airline or "",
                    departure_airport=rec.departure_airport or airport,
                    arrival_airport=rec.arrival_airport or "",
                    first_seen=rec.first_seen,
                    last_seen=rec.last_seen,
                )
                entries.append(entry)

                if rec.callsign.strip().upper() == hero_callsign.upper():
                    hero = entry

            chunk_start = chunk_end

            if len(entries) >= max_flights:
                logger.info("Reached max_flights=%d, stopping", max_flights)
                break

        if len(entries) >= max_flights:
            break

    manifest = FlightManifest(
        entries=entries,
        hero_flight=hero,
        window_start=window_start_utc,
        window_end=window_end_utc,
        query_airports=departure_airports,
    )

    logger.info(manifest.summary())
    return manifest
