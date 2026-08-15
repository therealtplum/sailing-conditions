"""NWS grid parsing — durations, ragged series, units and hazards."""

from __future__ import annotations

import datetime as dt
import json
from zoneinfo import ZoneInfo

import pytest

from sailing_conditions.sources.nws import (
    NwsClient,
    NwsError,
    UnsupportedUnit,
    build_hours,
    expand_series,
    parse_duration,
    parse_interval,
    weather_phrase,
)
from tests.conftest import CHICAGO, FixtureFetcher, load_fixture


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("PT1H", dt.timedelta(hours=1)),
        ("PT4H", dt.timedelta(hours=4)),
        ("P1D", dt.timedelta(days=1)),
        ("P7DT23H", dt.timedelta(days=7, hours=23)),
        ("PT30M", dt.timedelta(minutes=30)),
        ("PT1H30M", dt.timedelta(minutes=90)),
    ],
)
def test_parse_duration(text, expected):
    assert parse_duration(text) == expected


@pytest.mark.parametrize("text", ["", "P", "4H", "PT", "P1M", "nonsense"])
def test_parse_duration_rejects_junk(text):
    with pytest.raises(ValueError):
        parse_duration(text)


def test_parse_interval():
    start, duration = parse_interval("2026-08-15T02:00:00+00:00/PT4H")
    assert start == dt.datetime(2026, 8, 15, 2, tzinfo=dt.UTC)
    assert duration == dt.timedelta(hours=4)


def test_parse_interval_without_duration():
    with pytest.raises(ValueError):
        parse_interval("2026-08-15T02:00:00+00:00")


def test_expand_series_fills_every_hour_of_an_interval():
    element = {"uom": "wmoUnit:km_h-1", "values": [{"validTime": "2026-08-15T12:00:00+00:00/PT3H", "value": 18.52}]}
    series = expand_series(element, tz=dt.UTC)
    assert sorted(series) == [dt.datetime(2026, 8, 15, h, tzinfo=dt.UTC) for h in (12, 13, 14)]
    assert all(value == pytest.approx(10.0, abs=0.01) for value in series.values())


def test_expand_series_converts_into_local_time():
    element = {"uom": "wmoUnit:percent", "values": [{"validTime": "2026-08-15T12:00:00+00:00/PT1H", "value": 40}]}
    series = expand_series(element, tz=CHICAGO)
    assert next(iter(series)) == dt.datetime(2026, 8, 15, 7, tzinfo=CHICAGO)


def test_expand_series_converts_declared_units():
    metres = {"uom": "wmoUnit:m", "values": [{"validTime": "2026-08-15T12:00:00+00:00/PT1H", "value": 1.0}]}
    celsius = {"uom": "wmoUnit:degC", "values": [{"validTime": "2026-08-15T12:00:00+00:00/PT1H", "value": 20.0}]}
    assert next(iter(expand_series(metres, tz=dt.UTC).values())) == pytest.approx(3.28, abs=0.01)
    assert next(iter(expand_series(celsius, tz=dt.UTC).values())) == pytest.approx(68.0)


def test_unknown_unit_raises_rather_than_guessing():
    """A silent 1.6x error in wind speed is worse than a loud failure."""
    element = {"uom": "wmoUnit:furlong_fortnight-1", "values": [{"validTime": "2026-08-15T12:00:00+00:00/PT1H", "value": 5}]}
    with pytest.raises(UnsupportedUnit):
        expand_series(element, tz=dt.UTC)


def test_expand_series_skips_null_and_malformed_entries():
    element = {
        "uom": "wmoUnit:percent",
        "values": [
            {"validTime": "2026-08-15T12:00:00+00:00/PT1H", "value": None},
            {"validTime": "garbage", "value": 5},
            {"validTime": "2026-08-15T13:00:00+00:00/PT1H", "value": 25},
        ],
    }
    series = expand_series(element, tz=dt.UTC)
    assert list(series.values()) == [25]


def test_expand_series_of_nothing():
    assert expand_series(None, tz=dt.UTC) == {}


def test_weather_phrase():
    assert weather_phrase([{"coverage": "slight_chance", "weather": "rain_showers"}]) == "slight chance rain showers"
    assert weather_phrase([{"coverage": None, "weather": "fog", "intensity": "light"}]) == "light fog"
    assert weather_phrase([{"weather": None}]) is None
    assert weather_phrase([]) is None


def test_build_hours_from_the_recorded_grid():
    payload = json.loads(load_fixture("grid_chicago.json"))
    hours = build_hours(payload["properties"], tz=CHICAGO)

    assert hours, "fixture should contain forecast hours"
    assert all(h.time.tzinfo is CHICAGO for h in hours)
    assert hours == sorted(hours, key=lambda h: h.time)
    assert all(h.time - hours[0].time == dt.timedelta(hours=index) for index, h in enumerate(hours))

    first = hours[0]
    assert 0 <= first.wind_kt < 60
    assert first.wind_dir is not None
    assert first.sky_pct is not None and 0 <= first.sky_pct <= 100


def test_build_hours_requires_wind():
    with pytest.raises(NwsError):
        build_hours({"skyCover": {"uom": "wmoUnit:percent", "values": []}}, tz=CHICAGO)


def test_client_resolves_point_metadata(fetcher):
    grid = NwsClient(fetcher).point(41.939, -87.633)
    assert grid.office == "LOT"
    assert grid.timezone == "America/Chicago"
    assert grid.zone == ZoneInfo("America/Chicago")
    assert grid.grid_url.startswith("https://api.weather.gov/gridpoints/")


def test_client_rejects_a_point_without_a_grid():
    fetcher = FixtureFetcher()
    fetcher.routes = {"/points/": "alerts_active.json"}  # a payload with no properties
    with pytest.raises(NwsError):
        NwsClient(fetcher).point(41.9, -87.6)


def test_client_parses_hazards_and_skips_test_messages():
    fetcher = FixtureFetcher(alerts="alerts_marine.json")
    hazards = NwsClient(fetcher).hazards(41.939, -87.633, tz=CHICAGO)
    events = [h.event for h in hazards]
    assert events == ["Small Craft Advisory", "Special Marine Warning"]
    assert hazards[0].onset == dt.datetime(2026, 8, 15, 10, tzinfo=CHICAGO)
    assert hazards[0].covers(dt.datetime(2026, 8, 15, 12, tzinfo=CHICAGO))
    assert not hazards[0].covers(dt.datetime(2026, 8, 15, 21, tzinfo=CHICAGO))


def test_hazard_failures_are_not_fatal(fetcher):
    fetcher.fail_on("/alerts/active", RuntimeError("alerts down"))
    assert NwsClient(fetcher).hazards(41.939, -87.633) == []


def test_forecast_returns_grid_hours_and_hazards(fetcher, spot):
    grid, hours, hazards = NwsClient(fetcher).forecast(spot)
    assert grid.timezone == "America/Chicago"
    assert len(hours) > 12
    assert hazards == []


def test_spot_timezone_override_wins(fetcher, spot):
    from dataclasses import replace

    grid, hours, _ = NwsClient(fetcher).forecast(replace(spot, timezone="UTC"))
    assert grid.timezone == "UTC"
    assert hours[0].time.utcoffset() == dt.timedelta(0)
