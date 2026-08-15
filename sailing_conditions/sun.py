"""Sunrise, sunset and solar noon.

Implements NOAA's solar position algorithm — the one behind their public
calculator — including the equation of time, the eccentricity of Earth's
orbit and the nutation correction to obliquity. The simplified "sunrise
equation" found in most snippets is 2-4 minutes off at temperate
latitudes; this is within about half a minute, verified against
sunrise-sunset.org across latitudes from Key West to Seattle and at both
solstices (see ``tests/test_sun.py``).

Solar parameters are evaluated once at local midnight and then re-evaluated
at each estimated event time, which removes the residual error from the
sun's motion over the intervening hours.

The other half of the job is timezones: the algorithm works in absolute
instants (Julian dates), which are converted to UTC and only then localized
to the spot's IANA zone. Sunset is never accidentally reported in UTC or in
whatever zone the machine running the job happens to be in.
"""

from __future__ import annotations

import datetime as dt
import math
from zoneinfo import ZoneInfo

from .models import SunTimes

#: Solar altitude defining sunrise/sunset: 16' of solar semidiameter plus
#: 34' of atmospheric refraction below the geometric horizon.
SUNRISE_ALTITUDE_DEG = -0.833

#: Civil twilight — useful if you are deciding whether to sail home.
CIVIL_TWILIGHT_DEG = -6.0

J2000 = 2451545.0
_MINUTES_PER_DEGREE = 4.0


def julian_day_number(day: dt.date) -> int:
    """Julian Day Number for a proleptic Gregorian date (noon-based)."""
    a = (14 - day.month) // 12
    y = day.year + 4800 - a
    m = day.month + 12 * a - 3
    return day.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045


def _julian_century(julian_date: float) -> float:
    return (julian_date - J2000) / 36525.0


def solar_parameters(julian_date: float) -> tuple[float, float]:
    """Return ``(declination_degrees, equation_of_time_minutes)``.

    The equation of time is the difference between apparent and mean solar
    time — up to about 16 minutes over the year, and the single biggest
    source of error in naive sunrise code.
    """
    t = _julian_century(julian_date)

    mean_lon = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360.0
    mean_anomaly = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    eccentricity = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)

    anomaly_rad = math.radians(mean_anomaly)
    center = (
        math.sin(anomaly_rad) * (1.914602 - t * (0.004817 + 0.000014 * t))
        + math.sin(2 * anomaly_rad) * (0.019993 - 0.000101 * t)
        + math.sin(3 * anomaly_rad) * 0.000289
    )
    true_lon = mean_lon + center
    omega = 125.04 - 1934.136 * t
    apparent_lon = true_lon - 0.00569 - 0.00478 * math.sin(math.radians(omega))

    mean_obliquity = 23.0 + (26.0 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60.0) / 60.0
    obliquity = mean_obliquity + 0.00256 * math.cos(math.radians(omega))

    declination = math.degrees(
        math.asin(math.sin(math.radians(obliquity)) * math.sin(math.radians(apparent_lon)))
    )

    y = math.tan(math.radians(obliquity / 2.0)) ** 2
    mean_lon_rad = math.radians(mean_lon)
    equation_of_time = 4.0 * math.degrees(
        y * math.sin(2 * mean_lon_rad)
        - 2 * eccentricity * math.sin(anomaly_rad)
        + 4 * eccentricity * y * math.sin(anomaly_rad) * math.cos(2 * mean_lon_rad)
        - 0.5 * y * y * math.sin(4 * mean_lon_rad)
        - 1.25 * eccentricity * eccentricity * math.sin(2 * anomaly_rad)
    )
    return declination, equation_of_time


def _hour_angle(lat: float, declination_deg: float, altitude_deg: float) -> float | None:
    """Hour angle in degrees, or ``None`` during polar day/night."""
    phi = math.radians(lat)
    decl = math.radians(declination_deg)
    denominator = math.cos(phi) * math.cos(decl)
    if denominator == 0:
        return None
    cosine = math.cos(math.radians(90.0 - altitude_deg)) / denominator - math.tan(phi) * math.tan(decl)
    if cosine > 1.0 or cosine < -1.0:
        return None
    return math.degrees(math.acos(cosine))


def _to_local(day: dt.date, minutes_utc: float, tz: dt.tzinfo) -> dt.datetime:
    midnight = dt.datetime.combine(day, dt.time(0, 0), tzinfo=dt.UTC)
    moment = midnight + dt.timedelta(minutes=round(minutes_utc))
    return moment.astimezone(tz)


def sun_times(
    lat: float,
    lon: float,
    day: dt.date,
    tz: ZoneInfo | dt.tzinfo,
    *,
    altitude_deg: float = SUNRISE_ALTITUDE_DEG,
) -> SunTimes:
    """Compute solar events for a local date at a location.

    Args:
        lat: Latitude in degrees, positive north.
        lon: Longitude in degrees, positive east.
        day: Local calendar date.
        tz: Zone the results are expressed in.
        altitude_deg: Solar altitude defining the event; pass
            :data:`CIVIL_TWILIGHT_DEG` for twilight instead of sunrise.

    Returns:
        A :class:`~sailing_conditions.models.SunTimes`, rounded to the
        minute. During polar day or night ``sunrise`` and ``sunset`` are
        ``None`` and ``daylight_hours`` is 24.0 or 0.0.
    """
    midnight_jd = julian_day_number(day) - 0.5
    declination, equation_of_time = solar_parameters(midnight_jd)

    noon_minutes = 720.0 - _MINUTES_PER_DEGREE * lon - equation_of_time
    # Re-evaluate at the estimated transit: the sun moves while we compute.
    declination, equation_of_time = solar_parameters(midnight_jd + noon_minutes / 1440.0)
    noon_minutes = 720.0 - _MINUTES_PER_DEGREE * lon - equation_of_time
    solar_noon = _to_local(day, noon_minutes, tz)

    hour_angle = _hour_angle(lat, declination, altitude_deg)
    if hour_angle is None:
        # Which side of the horizon are we stuck on?
        noon_altitude = 90.0 - abs(lat - declination)
        daylight = 24.0 if noon_altitude > altitude_deg else 0.0
        return SunTimes(day, None, None, solar_noon, daylight)

    events: list[float] = []
    for sign in (-1.0, 1.0):
        minutes = noon_minutes + sign * hour_angle * _MINUTES_PER_DEGREE
        # One refinement pass at the estimated event time.
        event_declination, event_eot = solar_parameters(midnight_jd + minutes / 1440.0)
        event_angle = _hour_angle(lat, event_declination, altitude_deg)
        if event_angle is not None:
            minutes = (
                720.0
                - _MINUTES_PER_DEGREE * lon
                - event_eot
                + sign * event_angle * _MINUTES_PER_DEGREE
            )
        events.append(minutes)

    sunrise = _to_local(day, events[0], tz)
    sunset = _to_local(day, events[1], tz)
    daylight = (events[1] - events[0]) / 60.0
    return SunTimes(day, sunrise, sunset, solar_noon, round(daylight, 2))


def is_daylight(when: dt.datetime, sun: SunTimes, *, slot_minutes: int = 60) -> bool:
    """Whether a forecast slot beginning at ``when`` is mostly in daylight.

    A forecast hour is a *span*, not an instant: the slot labeled 7pm
    covers 7:00-8:00pm. It counts as daylight when its midpoint is between
    sunrise and sunset, so the last usable hour of the evening is included
    and the one after sunset is not.
    """
    if sun.polar_day:
        return True
    if sun.polar_night or sun.sunrise is None or sun.sunset is None:
        return False
    midpoint = when + dt.timedelta(minutes=slot_minutes / 2)
    return sun.sunrise <= midpoint <= sun.sunset
