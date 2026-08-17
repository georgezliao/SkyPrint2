"""Tier 2 Contrail Accountability Pipeline.

Retrospective analysis of NAT corridor flights using ERA5 + CoCiP.

Modules
-------
opensky_client
    OpenSky Network REST API client with OAuth2 auth.
manifest_builder
    Flight manifest construction from OpenSky departure data.
era5_fetcher
    ERA5 met + rad data download via pycontrails/cdsapi.
cocip_runner
    CoCiP evaluation with PSFlight aircraft performance.
counterfactual
    Altitude-offset counterfactual analysis.
ranking
    Airline ranking by contrail energy forcing.
run_pipeline
    Main orchestrator.
"""

__all__ = [
    "opensky_client",
    "manifest_builder",
    "era5_fetcher",
    "cocip_runner",
    "counterfactual",
    "ranking",
    "run_pipeline",
]
