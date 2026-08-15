"""Shared fixtures.

The suite never touches the network. ``FixtureFetcher`` implements the same
``Fetcher`` protocol as the real HTTP client and serves recorded payloads
from ``tests/fixtures`` (refresh them with ``tools/capture_fixtures.py``),
so the tests exercise the production code paths end to end.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from sailing_conditions.models import Hour, Score, ScoredHour, Spot, Verdict
from sailing_conditions.profiles import BUILTIN_PROFILES
from sailing_conditions.settings import Settings

FIXTURES = Path(__file__).parent / "fixtures"
CHICAGO = ZoneInfo("America/Chicago")

#: The instant the recorded fixtures were captured, used to freeze "now".
FIXTURE_NOW = dt.datetime(2026, 8, 15, 9, 30, tzinfo=dt.UTC)
FIXTURE_DATE = dt.date(2026, 8, 15)


def load_fixture(name: str) -> str:
    """Read a fixture file verbatim."""
    return (FIXTURES / name).read_text("utf-8")


class FixtureFetcher:
    """A :class:`~sailing_conditions.sources.http.Fetcher` backed by files.

    URLs are matched by substring, which keeps the routing table readable
    and means a change to query-string details does not break every test.
    """

    def __init__(self, routes: dict[str, str] | None = None, *, alerts: str = "alerts_active.json") -> None:
        self.routes = routes or {
            "/points/": "points_chicago.json",
            "/gridpoints/": "grid_chicago.json",
            "/alerts/active": alerts,
            "ndbc.noaa.gov": "ndbc_chii2.txt",
        }
        self.calls: list[str] = []
        self.failures: dict[str, Exception] = {}

    def fail_on(self, fragment: str, error: Exception) -> None:
        """Make any URL containing ``fragment`` raise ``error``."""
        self.failures[fragment] = error

    def get_text(self, url: str, *, ttl: float | None = None) -> str:
        """Serve a recorded payload for ``url``."""
        self.calls.append(url)
        for fragment, error in self.failures.items():
            if fragment in url:
                raise error
        for fragment, filename in self.routes.items():
            if fragment in url:
                return load_fixture(filename)
        raise AssertionError(f"no fixture registered for {url}")

    def get_json(self, url: str, *, ttl: float | None = None) -> Any:
        """Serve a recorded payload for ``url``, parsed as JSON."""
        return json.loads(self.get_text(url, ttl=ttl))


@pytest.fixture
def fetcher() -> FixtureFetcher:
    """A fetcher wired to the default recorded payloads."""
    return FixtureFetcher()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings that never touch the user's real home directory."""
    return Settings(
        contact="tests@example.com",
        cache_dir=None,
        state_path=tmp_path / "watch-state.json",
        spots=("chicago",),
    )


@pytest.fixture
def keelboat():
    """The default boat profile."""
    return BUILTIN_PROFILES["keelboat"]


@pytest.fixture
def spot() -> Spot:
    """A spot with a buoy, matching the recorded fixtures."""
    return Spot(
        key="chicago",
        name="Belmont Harbor",
        lat=41.939,
        lon=-87.633,
        region="Chicago, IL",
        buoy="CHII2",
        blurb="Test spot.",
    )


def make_hour(
    hour: int = 12,
    *,
    wind_kt: float = 12.0,
    day: dt.date = FIXTURE_DATE,
    tz: dt.tzinfo = CHICAGO,
    **kwargs: Any,
) -> Hour:
    """Build an :class:`Hour` with sensible defaults for scoring tests."""
    fields: dict[str, Any] = {
        "gust_kt": None,
        "wind_dir_deg": 225.0,
        "wave_ft": None,
        "temp_f": 72.0,
        "feels_like_f": 72.0,
        "precip_pct": 0.0,
        "thunder_pct": 0.0,
        "sky_pct": 20.0,
    }
    fields.update(kwargs)
    return Hour(time=dt.datetime(day.year, day.month, day.day, hour, tzinfo=tz), wind_kt=wind_kt, **fields)


def make_scored(hour: int, value: float, *, daylight: bool = True, day: dt.date = FIXTURE_DATE) -> ScoredHour:
    """Build a :class:`ScoredHour` with a fixed score, for window tests."""
    return ScoredHour(
        hour=make_hour(hour, day=day),
        score=Score(value=value, verdict=Verdict.from_score(value)),
        daylight=daylight,
    )
