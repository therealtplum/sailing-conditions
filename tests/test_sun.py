"""Solar calculations.

Expected values come from NOAA's algorithm as implemented by the ``astral``
library, cross-checked against published almanac times. Tolerance is 90
seconds — an order of magnitude tighter than the hourly resolution of the
forecast this feeds, and tight enough to catch the timezone bug this code
replaced (the old implementation stamped UTC minutes as local time).
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from sailing_conditions.sun import (
    CIVIL_TWILIGHT_DEG,
    is_daylight,
    julian_day_number,
    solar_parameters,
    sun_times,
)

TOLERANCE = dt.timedelta(seconds=90)

CASES = [
    # (name, lat, lon, tz, date, sunrise, sunset)
    ("chicago solstice", 41.939, -87.633, "America/Chicago", "2026-06-21", "05:15", "20:29"),
    ("chicago midwinter", 41.939, -87.633, "America/Chicago", "2026-12-21", "07:15", "16:22"),
    ("chicago dst start", 41.939, -87.633, "America/Chicago", "2026-03-08", "07:14", "18:48"),
    ("austin summer", 30.402, -97.918, "America/Chicago", "2026-08-15", "06:58", "20:12"),
    ("seattle spring", 47.681, -122.408, "America/Los_Angeles", "2026-03-10", "07:32", "19:07"),
    ("key west autumn", 24.556, -81.805, "America/New_York", "2026-11-02", "06:34", "17:46"),
    ("kaneohe winter", 21.440, -157.790, "Pacific/Honolulu", "2026-01-15", "07:11", "18:09"),
]


@pytest.mark.parametrize(("name", "lat", "lon", "tzname", "date", "rise", "set_"), CASES)
def test_matches_noaa_reference(name, lat, lon, tzname, date, rise, set_):
    tz = ZoneInfo(tzname)
    day = dt.date.fromisoformat(date)
    result = sun_times(lat, lon, day, tz)

    expected_rise = dt.datetime.combine(day, dt.time.fromisoformat(rise), tzinfo=tz)
    expected_set = dt.datetime.combine(day, dt.time.fromisoformat(set_), tzinfo=tz)

    assert result.sunrise is not None and result.sunset is not None
    assert abs(result.sunrise - expected_rise) <= TOLERANCE, f"{name} sunrise"
    assert abs(result.sunset - expected_set) <= TOLERANCE, f"{name} sunset"


def test_results_are_in_the_requested_zone():
    """The bug this replaced: UTC minutes reported as if they were local."""
    tz = ZoneInfo("America/Los_Angeles")
    result = sun_times(47.681, -122.408, dt.date(2026, 7, 4), tz)
    assert result.sunrise.tzinfo is tz
    assert result.sunrise.date() == dt.date(2026, 7, 4)
    assert 4 <= result.sunrise.hour <= 6, "a July sunrise in Seattle is not at noon"
    assert 20 <= result.sunset.hour <= 21


def test_solar_noon_sits_between_the_events():
    result = sun_times(41.939, -87.633, dt.date(2026, 5, 1), ZoneInfo("America/Chicago"))
    assert result.sunrise < result.solar_noon < result.sunset


def test_daylight_hours_match_the_events():
    result = sun_times(41.939, -87.633, dt.date(2026, 9, 1), ZoneInfo("America/Chicago"))
    measured = (result.sunset - result.sunrise).total_seconds() / 3600
    assert result.daylight_hours == pytest.approx(measured, abs=0.02)


def test_polar_day():
    result = sun_times(78.22, 15.63, dt.date(2026, 6, 21), ZoneInfo("Arctic/Longyearbyen"))
    assert result.polar_day
    assert result.sunrise is None and result.daylight_hours == 24.0


def test_polar_night():
    result = sun_times(78.22, 15.63, dt.date(2026, 12, 21), ZoneInfo("Arctic/Longyearbyen"))
    assert result.polar_night
    assert result.daylight_hours == 0.0


def test_civil_twilight_is_wider_than_sunrise():
    tz = ZoneInfo("America/Chicago")
    day = dt.date(2026, 8, 15)
    standard = sun_times(41.939, -87.633, day, tz)
    twilight = sun_times(41.939, -87.633, day, tz, altitude_deg=CIVIL_TWILIGHT_DEG)
    assert twilight.sunrise < standard.sunrise
    assert twilight.sunset > standard.sunset


def test_julian_day_number_reference_values():
    assert julian_day_number(dt.date(2000, 1, 1)) == 2451545
    assert julian_day_number(dt.date(2026, 8, 15)) == 2461268


def test_equation_of_time_has_the_right_sign_and_magnitude():
    """Around 3 November the sun runs ~16 minutes fast; in mid-February, slow."""
    november = solar_parameters(julian_day_number(dt.date(2026, 11, 3)) - 0.5)[1]
    february = solar_parameters(julian_day_number(dt.date(2026, 2, 11)) - 0.5)[1]
    assert 15.0 < november < 17.0
    assert -15.0 < february < -13.0


def test_declination_tracks_the_seasons():
    june = solar_parameters(julian_day_number(dt.date(2026, 6, 21)) - 0.5)[0]
    december = solar_parameters(julian_day_number(dt.date(2026, 12, 21)) - 0.5)[0]
    assert june == pytest.approx(23.44, abs=0.1)
    assert december == pytest.approx(-23.44, abs=0.1)


def test_is_daylight_judges_the_slot_not_the_instant():
    """A forecast hour counts when most of it is lit."""
    tz = ZoneInfo("America/Chicago")
    sun = sun_times(41.939, -87.633, dt.date(2026, 8, 15), tz)
    assert is_daylight(sun.sunrise + dt.timedelta(hours=2), sun)
    assert is_daylight(sun.sunset - dt.timedelta(minutes=45), sun), "mostly-lit hour counts"
    assert not is_daylight(sun.sunset - dt.timedelta(minutes=15), sun), "mostly-dark hour does not"
    assert not is_daylight(sun.sunset + dt.timedelta(hours=1), sun)
    assert not is_daylight(sun.sunrise - dt.timedelta(hours=2), sun)


def test_is_daylight_during_polar_extremes():
    tz = ZoneInfo("Arctic/Longyearbyen")
    midsummer = sun_times(78.22, 15.63, dt.date(2026, 6, 21), tz)
    midwinter = sun_times(78.22, 15.63, dt.date(2026, 12, 21), tz)
    when = dt.datetime(2026, 6, 21, 2, tzinfo=tz)
    assert is_daylight(when, midsummer)
    assert not is_daylight(when.replace(month=12), midwinter)
