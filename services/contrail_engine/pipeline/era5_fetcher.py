"""ERA5 meteorological and radiation data fetcher.

Downloads the variables CoCiP needs via the pycontrails ERA5 interface,
which wraps the CDS API (cdsapi >= 0.7.7).
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import xarray as xr

logger = logging.getLogger(__name__)

# Default cache directory for ERA5 grib/netcdf downloads
DEFAULT_CACHE_DIR = Path("data/era5_cache")


def fetch_era5_met(
    time_bounds: tuple[str, str],
    pressure_levels: list[int],
    bounding_box: dict[str, float],
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
) -> xr.Dataset:
    """Download ERA5 pressure-level meteorological data for CoCiP.

    Parameters
    ----------
    time_bounds : tuple[str, str]
        (start, end) ISO 8601 UTC timestamps.
    pressure_levels : list[int]
        Pressure levels in hPa, e.g. [200, 225, 250, 275, 300].
    bounding_box : dict
        {"lat_min", "lat_max", "lon_min", "lon_max"}.
    cache_dir : Path
        Local cache directory for downloaded files.

    Returns
    -------
    xr.Dataset
        Dataset ready for ``Cocip(met=..., ...)``.
    """
    from pycontrails.datalib.ecmwf import ERA5

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    start_dt = datetime.fromisoformat(time_bounds[0].replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(time_bounds[1].replace("Z", "+00:00"))

    # CoCiP met variables for ERA5 (ECMWF specific)
    met_variables = [
        "air_temperature",
        "specific_humidity",
        "eastward_wind",
        "northward_wind",
        "lagrangian_tendency_of_air_pressure",
        "specific_cloud_ice_water_content",
    ]

    logger.info(
        "Fetching ERA5 met: %s → %s, levels=%s",
        start_dt.isoformat(),
        end_dt.isoformat(),
        pressure_levels,
    )

    era5 = ERA5(
        time=time_bounds,
        variables=met_variables,
        pressure_levels=pressure_levels,
        cachestore=str(cache_dir),
    )

    met = era5.open_metdataset()
    logger.info("ERA5 met loaded: %s", list(met.data.data_vars))
    return met


def fetch_era5_rad(
    time_bounds: tuple[str, str],
    bounding_box: dict[str, float],
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
) -> xr.Dataset:
    """Download ERA5 single-level radiation data for CoCiP.

    Parameters
    ----------
    time_bounds : tuple[str, str]
        (start, end) ISO 8601 UTC timestamps.
    bounding_box : dict
        {"lat_min", "lat_max", "lon_min", "lon_max"}.
    cache_dir : Path
        Local cache directory.

    Returns
    -------
    xr.Dataset
        Radiation dataset for ``Cocip(rad=..., ...)``.
    """
    from pycontrails.datalib.ecmwf import ERA5

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    rad_variables = [
        "top_net_solar_radiation",
        "top_net_thermal_radiation",
    ]

    logger.info("Fetching ERA5 rad: %s → %s", time_bounds[0], time_bounds[1])

    era5 = ERA5(
        time=time_bounds,
        variables=rad_variables,
        cachestore=str(cache_dir),
    )

    rad = era5.open_metdataset()
    logger.info("ERA5 rad loaded: %s", list(rad.data.data_vars))
    return rad


def fetch_era5_data(
    time_bounds: tuple[str, str],
    pressure_levels: list[int],
    bounding_box: dict[str, float],
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
) -> tuple:
    """Convenience wrapper that fetches both met and rad datasets.

    Returns
    -------
    tuple[MetDataset, MetDataset]
        (met, rad) ready for CoCiP.
    """
    met = fetch_era5_met(time_bounds, pressure_levels, bounding_box, cache_dir)
    rad = fetch_era5_rad(time_bounds, bounding_box, cache_dir)
    return met, rad
