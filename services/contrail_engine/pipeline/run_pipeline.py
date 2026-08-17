"""Pipeline orchestrator — ties all modules together.

Runs the full Tier 2 Contrail Accountability Pipeline:
1. Build flight manifest from OpenSky
2. Fetch ADS-B tracks for each flight
3. Download ERA5 met/rad data
4. Run CoCiP baseline on each flight
5. Run counterfactual altitude offsets
6. Rank airlines by contrail impact
7. Serialize results
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default output directory
OUTPUT_DIR = Path("data/pipeline_output")


def _load_credentials() -> tuple[str, str]:
    """Load OpenSky OAuth2 credentials from environment."""
    client_id = os.environ.get("OPENSKY_CLIENT_ID", "")
    client_secret = os.environ.get("OPENSKY_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise RuntimeError(
            "OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET must be set. "
            "Check .env.local or environment variables."
        )
    return client_id, client_secret


def run_pipeline(
    output_dir: Path | str = OUTPUT_DIR,
    max_flights: int = 150,
    skip_era5: bool = False,
    hero_only: bool = False,
) -> dict[str, Any]:
    """Execute the full Tier 2 pipeline.

    Parameters
    ----------
    output_dir : Path
        Directory for JSON output files.
    max_flights : int
        Maximum flights to include in manifest.
    skip_era5 : bool
        If True, skip ERA5 download (for testing with pre-cached data).
    hero_only : bool
        If True, only process the hero flight (AA100).

    Returns
    -------
    dict
        Pipeline results including ranking report.
    """
    # Lazy imports to avoid loading heavy libraries at module level
    from constants import (
        COUNTERFACTUAL_OFFSETS_FT,
        ERA5_PRESSURE_LEVELS,
        FUEL_CONSTRAINT_PCT,
        NAT_BOUNDING_BOX,
        RETROSPECTIVE_WINDOW,
        TARGET_AIRLINES,
    )
    from pipeline.cocip_runner import (
        CoCiPResult,
        opensky_track_to_flight,
        run_cocip_batch,
    )
    from pipeline.counterfactual import run_counterfactual_batch
    from pipeline.era5_fetcher import fetch_era5_data
    from pipeline.manifest_builder import build_manifest
    from pipeline.opensky_client import OpenSkyClient
    from pipeline.ranking import rank_airlines

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    start_time = time.time()
    window_start = RETROSPECTIVE_WINDOW["start_utc"]
    window_end = RETROSPECTIVE_WINDOW["end_utc"]

    # ---- Step 1: Flight manifest ----
    logger.info("=" * 60)
    logger.info("STEP 1: Building flight manifest")
    logger.info("=" * 60)

    from pipeline.manifest_builder import FlightManifest, ManifestEntry

    manifest_path = output_dir / "manifest.json"

    if manifest_path.exists():
        logger.info("Manifest cache hit — loading from %s (skipping OpenSky)", manifest_path)
        with open(manifest_path) as f:
            cached = json.load(f)
        entries_loaded = [
            ManifestEntry(
                icao24=fl["icao24"],
                callsign=fl["callsign"],
                airline_icao=fl["airline"],
                departure_airport=fl["dep"],
                arrival_airport=fl["arr"],
                first_seen=fl["first_seen"],
                last_seen=fl["last_seen"],
            )
            for fl in cached["flights"]
        ]
        hero_callsign_cached = cached.get("hero")
        hero_entry = next(
            (e for e in entries_loaded if e.callsign == hero_callsign_cached), None
        )
        manifest = FlightManifest(
            entries=entries_loaded,
            hero_flight=hero_entry,
            window_start=cached["window"]["start"],
            window_end=cached["window"]["end"],
        )
        logger.info(
            "Loaded %d flights from cache (%s)",
            len(manifest.entries),
            manifest_path,
        )
        # Still need a client for Step 2 OpenSky fallback; credentials optional
        # if all tracks are already cached too.
        try:
            client_id, client_secret = _load_credentials()
            client = OpenSkyClient(client_id, client_secret)
        except RuntimeError:
            client = None  # type: ignore[assignment]
            logger.info("No OpenSky credentials — will use ADS-B Exchange / track cache only")
    else:
        client_id, client_secret = _load_credentials()
        client = OpenSkyClient(client_id, client_secret)

        manifest = build_manifest(
            client=client,
            target_airlines=TARGET_AIRLINES,
            window_start_utc=window_start,
            window_end_utc=window_end,
            hero_callsign="AAL100",
            max_flights=max_flights,
        )

        # Serialize manifest
        with open(manifest_path, "w") as f:
            json.dump(
                {
                    "n_flights": len(manifest.entries),
                    "window": {"start": window_start, "end": window_end},
                    "hero": manifest.hero_flight.callsign if manifest.hero_flight else None,
                    "airline_counts": manifest.airline_counts,
                    "flights": [
                        {
                            "icao24": e.icao24,
                            "callsign": e.callsign,
                            "airline": e.airline_icao,
                            "dep": e.departure_airport,
                            "arr": e.arrival_airport,
                            "first_seen": e.first_seen,
                            "last_seen": e.last_seen,
                        }
                        for e in manifest.entries
                    ],
                },
                f,
                indent=2,
            )
        logger.info("Manifest saved to %s", manifest_path)

    if hero_only and manifest.hero_flight:
        entries = [manifest.hero_flight]
        logger.info("Hero-only mode: processing AAL100 only")
    else:
        entries = manifest.entries

    # ---- Step 2: Fetch tracks ----
    logger.info("=" * 60)
    logger.info("STEP 2: Fetching ADS-B tracks (%d flights)", len(entries))
    logger.info("=" * 60)

    from pipeline.adsbexchange_client import _is_first_of_month, fetch_trace
    from pipeline.opensky_client import FlightTrack, TrackPoint

    tracks_cache_dir = output_dir / "tracks_cache"
    tracks_cache_dir.mkdir(parents=True, exist_ok=True)

    def _serialize_track(track: FlightTrack) -> dict:
        return {
            "icao24": track.icao24,
            "callsign": track.callsign,
            "start_time": track.start_time,
            "end_time": track.end_time,
            "path": [
                {
                    "time": p.time,
                    "latitude": p.latitude,
                    "longitude": p.longitude,
                    "baro_altitude_m": p.baro_altitude_m,
                    "heading": p.heading,
                    "on_ground": p.on_ground,
                }
                for p in track.path
            ],
        }

    def _deserialize_track(raw: dict) -> FlightTrack:
        return FlightTrack(
            icao24=raw["icao24"],
            callsign=raw["callsign"],
            start_time=raw["start_time"],
            end_time=raw["end_time"],
            path=[TrackPoint(**p) for p in raw["path"]],
        )

    flights_with_types: list[tuple[Any, str]] = []
    rate_limited = 0
    adsbx_hits = 0
    adsbx_misses = 0

    for entry in entries:
        cache_file = tracks_cache_dir / f"{entry.icao24}_{entry.first_seen}.json"

        if cache_file.exists():
            raw = json.loads(cache_file.read_text())
            track = _deserialize_track(raw)
            logger.debug("Track cache hit: %s", entry.callsign)
        else:
            track = None

            # Try ADS-B Exchange for 1st-of-month flights (free tier)
            if _is_first_of_month(entry.first_seen):
                track = fetch_trace(entry.icao24, entry.first_seen)
                if track is not None:
                    adsbx_hits += 1
                    logger.info("ADS-B Exchange hit: %s", entry.callsign)
                    cache_file.write_text(json.dumps(_serialize_track(track)))
                else:
                    adsbx_misses += 1
                    logger.debug("ADS-B Exchange miss: %s", entry.callsign)

            # Fall back to OpenSky for non-1st-of-month or ADS-B Exchange miss
            if track is None:
                if client is None:
                    rate_limited += 1
                    logger.warning(
                        "No track source for %s (no OpenSky credentials, ADS-B Exchange N/A)",
                        entry.callsign,
                    )
                    continue
                track = client.get_track(entry.icao24, entry.first_seen)
                if track is None:
                    rate_limited += 1
                    logger.warning("No track for %s (icao24=%s)", entry.callsign, entry.icao24)
                    continue
                cache_file.write_text(json.dumps(_serialize_track(track)))

        if len(track.path) < 10:
            logger.warning("Track too short for %s (%d pts)", entry.callsign, len(track.path))
            continue

        atype = entry.aircraft_type or "B77W"
        flight = opensky_track_to_flight(
            icao24=entry.icao24,
            callsign=entry.callsign,
            path=track.path,
            aircraft_type=atype,
        )
        if flight is not None:
            flights_with_types.append((flight, atype))

    if adsbx_hits or adsbx_misses:
        logger.info(
            "ADS-B Exchange: %d hits, %d misses (1st-of-month flights)",
            adsbx_hits, adsbx_misses,
        )
    if rate_limited:
        logger.warning(
            "%d/%d tracks skipped (rate limited / unavailable). "
            "Re-run tomorrow — cached tracks will not be re-fetched.",
            rate_limited, len(entries),
        )
    logger.info("Tracks retrieved: %d/%d", len(flights_with_types), len(entries))

    if not flights_with_types:
        logger.error("No valid tracks retrieved. Aborting pipeline.")
        return {"error": "No valid tracks", "manifest": str(manifest_path)}

    # ---- Step 3: ERA5 data ----
    logger.info("=" * 60)
    logger.info("STEP 3: Fetching ERA5 meteorological data")
    logger.info("=" * 60)

    met, rad = fetch_era5_data(
        time_bounds=(window_start, window_end),
        pressure_levels=ERA5_PRESSURE_LEVELS,
        bounding_box=NAT_BOUNDING_BOX,
        cache_dir=output_dir / "era5_cache",
    )

    # ---- Step 4: CoCiP baseline ----
    logger.info("=" * 60)
    logger.info("STEP 4: Running CoCiP baseline (%d flights)", len(flights_with_types))
    logger.info("=" * 60)

    cocip_results = run_cocip_batch(flights_with_types, met, rad)

    # Serialize CoCiP results
    cocip_path = output_dir / "cocip_results.json"
    with open(cocip_path, "w") as f:
        json.dump(
            [
                {
                    "flight_id": r.flight_id,
                    "callsign": r.callsign,
                    "airline_icao": r.airline_icao,
                    "aircraft_type": r.aircraft_type,
                    "energy_forcing_j": r.energy_forcing_j,
                    "ef_per_km": r.ef_per_km,
                    "contrail_persistent": r.contrail_persistent,
                    "fuel_burn_kg": r.fuel_burn_kg,
                    "co2_kg": r.co2_kg,
                    "distance_km": r.flight_distance_km,
                    "cruise_alt_mean_ft": r.cruise_alt_mean_ft,
                    "sac_frac": r.sac_satisfied_frac,
                }
                for r in cocip_results
            ],
            f,
            indent=2,
        )
    logger.info("CoCiP results saved to %s", cocip_path)

    # ---- Step 5: Counterfactual analysis ----
    logger.info("=" * 60)
    logger.info("STEP 5: Counterfactual altitude analysis")
    logger.info("=" * 60)

    # Build tuples: (flight, aircraft_type, baseline_ef, baseline_fuel)
    # Match flights to CoCiP results by flight_id
    cocip_by_id = {r.flight_id: r for r in cocip_results}
    cf_inputs: list[tuple[Any, str, float, float]] = []
    for flight, atype in flights_with_types:
        fid = flight.attrs.get("flight_id", "")
        if fid in cocip_by_id:
            cr = cocip_by_id[fid]
            # Only run counterfactual on warming flights
            if cr.energy_forcing_j > 0:
                cf_inputs.append((flight, atype, cr.energy_forcing_j, cr.fuel_burn_kg))

    logger.info("Running counterfactual on %d warming flights", len(cf_inputs))

    cf_results = run_counterfactual_batch(
        cf_inputs,
        met,
        rad,
        offsets_ft=COUNTERFACTUAL_OFFSETS_FT,
        fuel_constraint_pct=FUEL_CONSTRAINT_PCT,
    )

    # Serialize counterfactual results
    cf_path = output_dir / "counterfactual_results.json"
    with open(cf_path, "w") as f:
        json.dump(
            [
                {
                    "flight_id": r.flight_id,
                    "callsign": r.callsign,
                    "airline": r.airline_icao,
                    "baseline_ef_j": r.baseline_ef_j,
                    "best_offset_ft": r.best_offset_ft,
                    "best_ef_j": r.best_ef_j,
                    "avoidable": r.avoidable,
                    "max_reduction_pct": r.max_ef_reduction_pct,
                    "fuel_penalty_pct": r.best_fuel_penalty_pct,
                    "scenarios": [
                        {
                            "offset_ft": s.offset_ft,
                            "ef_j": s.energy_forcing_j,
                            "fuel_kg": s.fuel_burn_kg,
                            "fuel_penalty_pct": s.fuel_penalty_pct,
                        }
                        for s in r.scenarios
                    ],
                }
                for r in cf_results
            ],
            f,
            indent=2,
        )
    logger.info("Counterfactual results saved to %s", cf_path)

    # ---- Step 6: Airline ranking ----
    logger.info("=" * 60)
    logger.info("STEP 6: Computing airline rankings")
    logger.info("=" * 60)

    report = rank_airlines(
        cocip_results=cocip_results,
        counterfactual_results=cf_results,
        airline_names=TARGET_AIRLINES,
        hero_callsign="AAL100",
    )

    # Serialize ranking
    ranking_path = output_dir / "ranking_report.json"
    with open(ranking_path, "w") as f:
        json.dump(report.to_dict(), f, indent=2)
    logger.info("Ranking report saved to %s", ranking_path)

    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info(
        "Pipeline complete in %.1f min: %d flights, %d warming, %d avoidable",
        elapsed / 60,
        report.total_flights,
        report.total_warming,
        report.total_avoidable,
    )
    logger.info("=" * 60)

    return {
        "manifest_path": str(manifest_path),
        "cocip_path": str(cocip_path),
        "counterfactual_path": str(cf_path),
        "ranking_path": str(ranking_path),
        "elapsed_s": elapsed,
        "ranking": report.to_dict(),
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    result = run_pipeline()
    print(json.dumps(result.get("ranking", {}), indent=2))
