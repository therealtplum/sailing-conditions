"""
sailing-conditions: Quick sailing condition summaries across multiple cities.

This package provides tools for fetching and analyzing sailing conditions
from the National Weather Service (NWS) API.

Example usage:
    from sailing_conditions import chicago_forecast, marine_city_forecast
    
    forecast = chicago_forecast("TODAY")
    print(forecast["rating"])  # 1-10 rating
"""
from __future__ import annotations

from .forecast import (
    chicago_forecast,
    marine_city_forecast,
    grid_city_forecast,
)
from .parsers import (
    parse_wind,
    parse_waves,
    parse_sky,
    compute_rating,
)
from .fetchers import (
    fetch_grid_periods,
    fetch_city_marine_text,
)
from .cities import CITIES
from .config import DEFAULT_KEYS

__all__ = [
    # Forecast functions
    "chicago_forecast",
    "marine_city_forecast",
    "grid_city_forecast",
    # Parsers
    "parse_wind",
    "parse_waves",
    "parse_sky",
    "compute_rating",
    # Fetchers
    "fetch_grid_periods",
    "fetch_city_marine_text",
    # Data
    "CITIES",
    "DEFAULT_KEYS",
]

__version__ = "0.1.0"
