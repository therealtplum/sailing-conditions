"""Unit conversions and meteorological helpers.

Everything inside the package is normalized to a single set of units the
moment it crosses the network boundary:

==========  ========
quantity    unit
==========  ========
wind        knots
waves       feet
temperature degrees Fahrenheit
direction   degrees true
==========  ========

The NWS API speaks km/h, metres and degrees Celsius; NDBC speaks m/s and
metres. Convert once, in the source layer, and never think about it again.
"""

from __future__ import annotations

KMH_TO_KNOTS = 0.5399568
MS_TO_KNOTS = 1.9438445
M_TO_FEET = 3.2808399

#: 16-point compass rose, indexed by ``round(deg / 22.5) % 16``.
COMPASS_POINTS = (
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
)

#: Beaufort force upper bounds in knots (force 0..12).
_BEAUFORT_MAX_KT = (1, 3, 6, 10, 16, 21, 27, 33, 40, 47, 55, 63)

_BEAUFORT_LABELS = (
    "calm", "light air", "light breeze", "gentle breeze", "moderate breeze",
    "fresh breeze", "strong breeze", "near gale", "gale", "strong gale",
    "storm", "violent storm", "hurricane force",
)


def kmh_to_knots(value: float) -> float:
    """Convert kilometres per hour to knots."""
    return value * KMH_TO_KNOTS


def ms_to_knots(value: float) -> float:
    """Convert metres per second to knots."""
    return value * MS_TO_KNOTS


def metres_to_feet(value: float) -> float:
    """Convert metres to feet."""
    return value * M_TO_FEET


def celsius_to_fahrenheit(value: float) -> float:
    """Convert degrees Celsius to degrees Fahrenheit."""
    return value * 9.0 / 5.0 + 32.0


def fahrenheit_to_celsius(value: float) -> float:
    """Convert degrees Fahrenheit to degrees Celsius."""
    return (value - 32.0) * 5.0 / 9.0


def compass(degrees: float | None) -> str | None:
    """Return the 16-point compass abbreviation for a true bearing.

    ``None`` in, ``None`` out — NWS omits wind direction in calm conditions.
    """
    if degrees is None:
        return None
    return COMPASS_POINTS[round(degrees / 22.5) % 16]


def beaufort(knots: float) -> int:
    """Return the Beaufort force (0-12) for a sustained wind speed."""
    for force, upper in enumerate(_BEAUFORT_MAX_KT):
        if knots <= upper:
            return force
    return 12


def beaufort_label(knots: float) -> str:
    """Return the descriptive Beaufort name for a sustained wind speed."""
    return _BEAUFORT_LABELS[beaufort(knots)]


def gust_ratio(wind_kt: float, gust_kt: float | None) -> float | None:
    """Gust factor: peak gust divided by sustained wind.

    Below 3 kt the ratio is numerically unstable (a 1 kt breeze gusting to
    3 kt is not "3x gusty" in any meaningful sense), so it is reported as
    ``None`` and the caller should skip the gust penalty entirely.
    """
    if gust_kt is None or wind_kt < 3.0:
        return None
    return max(1.0, gust_kt / wind_kt)


def clamp(value: float, low: float, high: float) -> float:
    """Clamp ``value`` into ``[low, high]``."""
    return max(low, min(high, value))
