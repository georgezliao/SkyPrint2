"""Counterfactual altitude analysis for contrail avoidance.

For each flight, applies altitude offsets to the cruise portion and re-runs
CoCiP to quantify the energy forcing at alternative altitudes. Checks that
the fuel penalty stays within the FUEL_CONSTRAINT_PCT limit.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class CounterfactualScenario:
    """One altitude-offset scenario for a single flight."""

    offset_ft: int
    energy_forcing_j: float
    fuel_burn_kg: float
    fuel_penalty_pct: float
    contrail_persistent: bool
    n_contrail_waypoints: int


@dataclass
class CounterfactualResult:
    """Full counterfactual analysis for one flight."""

    flight_id: str
    callsign: str
    airline_icao: str
    aircraft_type: str
    baseline_ef_j: float
    baseline_fuel_kg: float
    scenarios: list[CounterfactualScenario] = field(default_factory=list)
    best_offset_ft: int = 0
    best_ef_j: float = 0.0
    best_fuel_penalty_pct: float = 0.0
    avoidable: bool = False  # True if any feasible offset eliminates warming contrails
    max_ef_reduction_pct: float = 0.0

    @property
    def warming(self) -> bool:
        return self.baseline_ef_j > 0


def _shift_cruise_altitude(
    flight: Any,
    offset_ft: int,
    cruise_min_alt_ft: int = 30000,
) -> Any:
    """Create a copy of the flight with cruise altitudes shifted.

    Only waypoints above cruise_min_alt_ft are shifted. The shift is applied
    in meters (offset_ft * 0.3048).
    """
    shifted = copy.deepcopy(flight)
    df = shifted.dataframe

    offset_m = offset_ft * 0.3048
    alt_ft = df["altitude"] * 3.28084  # altitude is in meters
    cruise_mask = alt_ft >= cruise_min_alt_ft

    df.loc[cruise_mask, "altitude"] = df.loc[cruise_mask, "altitude"] + offset_m

    # Clamp to reasonable bounds (FL200–FL500)
    min_alt_m = 6096  # ~20000 ft
    max_alt_m = 15240  # ~50000 ft
    df["altitude"] = df["altitude"].clip(lower=min_alt_m, upper=max_alt_m)

    shifted.update(df)
    return shifted


def run_counterfactual(
    flight: Any,
    met: Any,
    rad: Any,
    aircraft_type: str,
    baseline_ef_j: float,
    baseline_fuel_kg: float,
    offsets_ft: list[int] | None = None,
    fuel_constraint_pct: float = 2.0,
    cruise_min_alt_ft: int = 30000,
) -> CounterfactualResult:
    """Run counterfactual altitude analysis for a single flight.

    Parameters
    ----------
    flight : pycontrails.core.flight.Flight
        Original flight trajectory.
    met, rad : MetDataset
        Meteorological data (shared across scenarios).
    aircraft_type : str
        ICAO type designator.
    baseline_ef_j : float
        Energy forcing from the baseline CoCiP run.
    baseline_fuel_kg : float
        Fuel burn from the baseline CoCiP run.
    offsets_ft : list[int]
        Altitude offsets to test. Defaults to [-4000, -2000, 0, 2000, 4000].
    fuel_constraint_pct : float
        Maximum acceptable fuel penalty [%].
    cruise_min_alt_ft : int
        Minimum altitude for cruise phase identification.

    Returns
    -------
    CounterfactualResult
    """
    from pipeline.cocip_runner import run_cocip_single

    if offsets_ft is None:
        offsets_ft = [-4000, -2000, 0, 2000, 4000]

    callsign = flight.attrs.get("callsign", "unknown")
    flight_id = flight.attrs.get("flight_id", callsign)
    airline_icao = callsign[:3] if len(callsign) >= 3 else ""

    scenarios: list[CounterfactualScenario] = []

    for offset in offsets_ft:
        if offset == 0:
            # Baseline scenario — already computed
            scenarios.append(CounterfactualScenario(
                offset_ft=0,
                energy_forcing_j=baseline_ef_j,
                fuel_burn_kg=baseline_fuel_kg,
                fuel_penalty_pct=0.0,
                contrail_persistent=baseline_ef_j != 0,
                n_contrail_waypoints=0,  # will be filled from baseline
            ))
            continue

        shifted = _shift_cruise_altitude(flight, offset, cruise_min_alt_ft)
        result = run_cocip_single(shifted, met, rad, aircraft_type)

        if result is None:
            logger.warning(
                "CoCiP failed for %s offset=%+dft, skipping", callsign, offset
            )
            continue

        fuel_penalty = 0.0
        if baseline_fuel_kg > 0:
            fuel_penalty = (
                (result.fuel_burn_kg - baseline_fuel_kg) / baseline_fuel_kg * 100.0
            )

        scenarios.append(CounterfactualScenario(
            offset_ft=offset,
            energy_forcing_j=result.energy_forcing_j,
            fuel_burn_kg=result.fuel_burn_kg,
            fuel_penalty_pct=fuel_penalty,
            contrail_persistent=result.contrail_persistent,
            n_contrail_waypoints=result.n_contrail_waypoints,
        ))

    # Find best feasible scenario (minimum EF within fuel constraint)
    feasible = [
        s for s in scenarios
        if s.fuel_penalty_pct <= fuel_constraint_pct
    ]

    best_offset = 0
    best_ef = baseline_ef_j
    best_penalty = 0.0
    avoidable = False
    max_reduction = 0.0

    if feasible:
        best = min(feasible, key=lambda s: s.energy_forcing_j)
        best_offset = best.offset_ft
        best_ef = best.energy_forcing_j
        best_penalty = best.fuel_penalty_pct

        if baseline_ef_j > 0:
            reduction = (baseline_ef_j - best_ef) / baseline_ef_j * 100.0
            max_reduction = max(0.0, reduction)
            # "Avoidable" if best scenario eliminates warming contrails
            # or reduces EF by >80%
            avoidable = best_ef <= 0 or max_reduction > 80.0

    return CounterfactualResult(
        flight_id=flight_id,
        callsign=callsign,
        airline_icao=airline_icao,
        aircraft_type=aircraft_type,
        baseline_ef_j=baseline_ef_j,
        baseline_fuel_kg=baseline_fuel_kg,
        scenarios=scenarios,
        best_offset_ft=best_offset,
        best_ef_j=best_ef,
        best_fuel_penalty_pct=best_penalty,
        avoidable=avoidable,
        max_ef_reduction_pct=max_reduction,
    )


def run_counterfactual_batch(
    flights_with_results: list[tuple[Any, str, float, float]],
    met: Any,
    rad: Any,
    offsets_ft: list[int] | None = None,
    fuel_constraint_pct: float = 2.0,
) -> list[CounterfactualResult]:
    """Run counterfactual analysis on a batch of flights.

    Parameters
    ----------
    flights_with_results : list of (Flight, aircraft_type, baseline_ef, baseline_fuel)
    met, rad : MetDataset
    offsets_ft : list[int], optional
    fuel_constraint_pct : float

    Returns
    -------
    list[CounterfactualResult]
    """
    results = []
    for i, (flight, atype, ef, fuel) in enumerate(flights_with_results):
        cs = flight.attrs.get("callsign", f"flight_{i}")
        logger.info(
            "Counterfactual %d/%d: %s (baseline EF=%.2e J)",
            i + 1, len(flights_with_results), cs, ef,
        )
        result = run_counterfactual(
            flight, met, rad, atype, ef, fuel,
            offsets_ft=offsets_ft,
            fuel_constraint_pct=fuel_constraint_pct,
        )
        results.append(result)

    n_avoidable = sum(1 for r in results if r.avoidable)
    n_warming = sum(1 for r in results if r.warming)
    logger.info(
        "Counterfactual batch: %d flights, %d warming, %d avoidable",
        len(results), n_warming, n_avoidable,
    )
    return results
