"""Unit conversions and meteorological helpers."""

from __future__ import annotations

import pytest

from sailing_conditions.units import (
    beaufort,
    beaufort_label,
    celsius_to_fahrenheit,
    clamp,
    compass,
    fahrenheit_to_celsius,
    gust_ratio,
    kmh_to_knots,
    metres_to_feet,
    ms_to_knots,
)


@pytest.mark.parametrize(
    ("kmh", "expected_kt"),
    [(0, 0), (1.852, 1.0), (18.52, 10.0), (37.04, 20.0)],
)
def test_kmh_to_knots(kmh, expected_kt):
    assert kmh_to_knots(kmh) == pytest.approx(expected_kt, abs=0.01)


def test_ms_to_knots_matches_definition():
    # 1 knot is exactly 1852 m / 3600 s.
    assert ms_to_knots(1852 / 3600) == pytest.approx(1.0, abs=1e-4)


def test_metres_to_feet():
    assert metres_to_feet(1.0) == pytest.approx(3.28084, abs=1e-4)


def test_temperature_round_trip():
    assert celsius_to_fahrenheit(0) == 32
    assert celsius_to_fahrenheit(100) == 212
    assert fahrenheit_to_celsius(celsius_to_fahrenheit(21.5)) == pytest.approx(21.5)


@pytest.mark.parametrize(
    ("degrees", "point"),
    [(0, "N"), (11, "N"), (12, "NNE"), (90, "E"), (180, "S"), (270, "W"), (359, "N"), (360, "N")],
)
def test_compass_points(degrees, point):
    assert compass(degrees) == point


def test_compass_passes_through_none():
    # NWS omits wind direction when it is calm; that must not become "N".
    assert compass(None) is None


@pytest.mark.parametrize(
    ("knots", "force"),
    [(0, 0), (1, 0), (3, 1), (10, 3), (16, 4), (27, 6), (40, 8), (70, 12)],
)
def test_beaufort_scale(knots, force):
    assert beaufort(knots) == force


def test_beaufort_label():
    assert beaufort_label(0) == "calm"
    assert beaufort_label(12) == "moderate breeze"


def test_gust_ratio_is_none_in_light_air():
    # 1 kt gusting 3 kt is not "3x gusty" in any useful sense.
    assert gust_ratio(1.0, 3.0) is None


def test_gust_ratio_never_below_one():
    assert gust_ratio(15.0, 12.0) == 1.0
    assert gust_ratio(10.0, 15.0) == pytest.approx(1.5)


def test_gust_ratio_without_gust_data():
    assert gust_ratio(12.0, None) is None


def test_clamp():
    assert clamp(-1, 0, 10) == 0
    assert clamp(11, 0, 10) == 10
    assert clamp(5, 0, 10) == 5
