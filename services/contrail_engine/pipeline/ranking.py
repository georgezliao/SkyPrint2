"""Airline ranking and scoring from CoCiP + counterfactual results.

Aggregates per-flight energy forcing into per-airline scores. Requires
MIN_FLIGHTS_FOR_RANKING flights per airline for a valid ranking.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from pipeline.cocip_runner import CoCiPResult
from pipeline.counterfactual import CounterfactualResult

logger = logging.getLogger(__name__)

# From constants.py — duplicated here to avoid circular import at module level
_MIN_FLIGHTS = 30


@dataclass
class AirlineScore:
    """Aggregated contrail score for one airline."""

    airline_icao: str
    airline_name: str
    n_flights: int
    n_warming_contrails: int
    n_avoidable: int

    # Energy forcing totals [J]
    total_ef_j: float
    mean_ef_per_flight_j: float
    mean_ef_per_km_j: float

    # Fuel / CO2
    total_fuel_kg: float
    total_co2_kg: float

    # Avoidability
    avoidability_ratio: float  # fraction of warming flights that are avoidable
    mean_ef_reduction_pct: float  # mean max EF reduction across avoidable flights

    # Rank (1 = worst contrail impact)
    rank: int = 0
    valid: bool = True  # False if n_flights < MIN_FLIGHTS


@dataclass
class RankingReport:
    """Complete ranking output."""

    airlines: list[AirlineScore] = field(default_factory=list)
    total_flights: int = 0
    total_warming: int = 0
    total_avoidable: int = 0
    hero_flight_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "total_flights": self.total_flights,
            "total_warming": self.total_warming,
            "total_avoidable": self.total_avoidable,
            "airlines": [
                {
                    "rank": a.rank,
                    "airline_icao": a.airline_icao,
                    "airline_name": a.airline_name,
                    "n_flights": a.n_flights,
                    "n_warming_contrails": a.n_warming_contrails,
                    "n_avoidable": a.n_avoidable,
                    "total_ef_j": a.total_ef_j,
                    "mean_ef_per_flight_j": a.mean_ef_per_flight_j,
                    "mean_ef_per_km_j": a.mean_ef_per_km_j,
                    "avoidability_ratio": a.avoidability_ratio,
                    "mean_ef_reduction_pct": a.mean_ef_reduction_pct,
                    "valid": a.valid,
                }
                for a in self.airlines
            ],
            "hero_flight": self.hero_flight_summary,
        }


def rank_airlines(
    cocip_results: list[CoCiPResult],
    counterfactual_results: list[CounterfactualResult],
    airline_names: dict[str, str],
    min_flights: int = _MIN_FLIGHTS,
    hero_callsign: str = "AAL100",
) -> RankingReport:
    """Rank airlines by total energy forcing.

    Parameters
    ----------
    cocip_results : list[CoCiPResult]
        Baseline CoCiP results for all flights.
    counterfactual_results : list[CounterfactualResult]
        Counterfactual results for all flights.
    airline_names : dict[str, str]
        ICAO code → airline name.
    min_flights : int
        Minimum flights for valid ranking.
    hero_callsign : str
        Callsign to extract as hero flight summary.

    Returns
    -------
    RankingReport
    """
    # Index counterfactual results by flight_id
    cf_by_id: dict[str, CounterfactualResult] = {
        r.flight_id: r for r in counterfactual_results
    }

    # Group by airline
    by_airline: dict[str, list[CoCiPResult]] = {}
    for r in cocip_results:
        by_airline.setdefault(r.airline_icao, []).append(r)

    scores: list[AirlineScore] = []

    for icao, flights in by_airline.items():
        n = len(flights)
        n_warming = sum(1 for f in flights if f.energy_forcing_j > 0)

        total_ef = sum(f.energy_forcing_j for f in flights)
        total_fuel = sum(f.fuel_burn_kg for f in flights)
        total_co2 = sum(f.co2_kg for f in flights)
        total_dist = sum(f.flight_distance_km for f in flights)

        mean_ef = total_ef / n if n > 0 else 0.0
        mean_ef_km = total_ef / total_dist if total_dist > 0 else 0.0

        # Avoidability from counterfactual
        avoidable_flights = [
            cf_by_id[f.flight_id]
            for f in flights
            if f.flight_id in cf_by_id and cf_by_id[f.flight_id].avoidable
        ]
        n_avoidable = len(avoidable_flights)
        avoidability = n_avoidable / n_warming if n_warming > 0 else 0.0

        mean_reduction = 0.0
        if avoidable_flights:
            mean_reduction = sum(
                af.max_ef_reduction_pct for af in avoidable_flights
            ) / len(avoidable_flights)

        scores.append(AirlineScore(
            airline_icao=icao,
            airline_name=airline_names.get(icao, icao),
            n_flights=n,
            n_warming_contrails=n_warming,
            n_avoidable=n_avoidable,
            total_ef_j=total_ef,
            mean_ef_per_flight_j=mean_ef,
            mean_ef_per_km_j=mean_ef_km,
            total_fuel_kg=total_fuel,
            total_co2_kg=total_co2,
            avoidability_ratio=avoidability,
            mean_ef_reduction_pct=mean_reduction,
            valid=n >= min_flights,
        ))

    # Sort by total EF descending (worst first)
    scores.sort(key=lambda s: s.total_ef_j, reverse=True)
    for i, s in enumerate(scores):
        s.rank = i + 1

    # Hero flight summary
    hero_summary: dict[str, Any] = {}
    for r in cocip_results:
        if r.callsign.strip().upper() == hero_callsign.upper():
            hero_summary = {
                "callsign": r.callsign,
                "airline_icao": r.airline_icao,
                "aircraft_type": r.aircraft_type,
                "energy_forcing_j": r.energy_forcing_j,
                "ef_per_km": r.ef_per_km,
                "contrail_persistent": r.contrail_persistent,
                "fuel_burn_kg": r.fuel_burn_kg,
                "co2_kg": r.co2_kg,
                "distance_km": r.flight_distance_km,
            }
            if r.flight_id in cf_by_id:
                cf = cf_by_id[r.flight_id]
                hero_summary["avoidable"] = cf.avoidable
                hero_summary["best_offset_ft"] = cf.best_offset_ft
                hero_summary["max_ef_reduction_pct"] = cf.max_ef_reduction_pct
            break

    total_warming = sum(s.n_warming_contrails for s in scores)
    total_avoidable = sum(s.n_avoidable for s in scores)

    report = RankingReport(
        airlines=scores,
        total_flights=len(cocip_results),
        total_warming=total_warming,
        total_avoidable=total_avoidable,
        hero_flight_summary=hero_summary,
    )

    logger.info(
        "Ranking: %d airlines, %d flights, %d warming, %d avoidable",
        len(scores), report.total_flights, total_warming, total_avoidable,
    )
    return report
