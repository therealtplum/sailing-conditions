"""Data sources: everything that touches the network lives behind here.

The layer exposes exactly one dependency to the rest of the package — the
:class:`~sailing_conditions.sources.http.Fetcher` protocol — so the domain
code has no idea whether its bytes came from api.weather.gov or a fixture
file on disk.
"""

from .http import DiskCache, Fetcher, FetchError, HttpClient
from .ndbc import NdbcClient, parse_realtime
from .nws import GridPoint, NwsClient, NwsError, build_hours, parse_duration, parse_interval

__all__ = [
    "DiskCache",
    "FetchError",
    "Fetcher",
    "GridPoint",
    "HttpClient",
    "NdbcClient",
    "NwsClient",
    "NwsError",
    "build_hours",
    "parse_duration",
    "parse_interval",
    "parse_realtime",
]
