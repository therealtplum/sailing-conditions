"""National Weather Service API client.

The previous version of this project scraped prose forecast products with
regular expressions — ``"west wind 10 to 15 mph"`` parsed back into numbers.
NWS also publishes the *grid* those sentences are generated from:

``/gridpoints/{office}/{x},{y}`` returns every forecast element as a typed
time series with declared units — wind speed, gusts, direction, wave
height, probability of thunder, sky cover, apparent temperature — at native
hourly resolution. That is what this client consumes.

Two wrinkles are worth knowing about:

*Ragged time series.* Each element carries its own ``validTime`` intervals
in ISO-8601 ``start/duration`` form, and the intervals differ per element:
wind might be published in 4-hour blocks while sky cover is hourly. Every
series is therefore expanded onto a common hourly index before assembly.

*Declared units.* Values arrive as ``wmoUnit:km_h-1``, ``wmoUnit:degC`` and
friends. Conversion is driven by the declared unit rather than assumed, and
an unrecognized unit raises rather than silently passing a wrong number
downstream — a 1.6x error in wind speed is the kind of bug that ruins a
weekend.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

from ..models import Hazard, Hour, Spot
from ..units import celsius_to_fahrenheit, kmh_to_knots, metres_to_feet, ms_to_knots
from .http import Fetcher

NWS_API = "https://api.weather.gov"

#: Point metadata (grid coordinates, timezone) effectively never changes.
POINT_TTL = 30 * 24 * 3600
#: Grids are updated roughly hourly; half an hour keeps runs snappy and polite.
GRID_TTL = 30 * 60
#: Warnings can be issued at any moment, so cache them only briefly.
ALERT_TTL = 5 * 60

_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+(?:\.\d+)?)D)?"
    r"(?:T(?:(?P<hours>\d+(?:\.\d+)?)H)?"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$"
)

_IDENTITY: Callable[[float], float] = lambda value: value  # noqa: E731

#: Declared WMO unit -> converter into this package's canonical units.
UNIT_CONVERTERS: Mapping[str | None, Callable[[float], float]] = {
    None: _IDENTITY,
    "": _IDENTITY,
    "wmoUnit:km_h-1": kmh_to_knots,
    "wmoUnit:m_s-1": ms_to_knots,
    "wmoUnit:m": metres_to_feet,
    "wmoUnit:degC": celsius_to_fahrenheit,
    "wmoUnit:degF": _IDENTITY,
    "wmoUnit:percent": _IDENTITY,
    "wmoUnit:degree_(angle)": _IDENTITY,
    "wmoUnit:ft": _IDENTITY,
    "wmoUnit:s": _IDENTITY,
    "nwsUnit:s": _IDENTITY,
}

#: Alerts that are informational rather than operational.
_IGNORED_ALERT_STATUSES = frozenset({"test", "draft", "exercise", "system"})


class NwsError(RuntimeError):
    """The API responded, but not with the shape we need."""


class UnsupportedUnit(NwsError):
    """A grid element declared a unit this client does not know how to convert."""


@dataclass(frozen=True, slots=True)
class GridPoint:
    """Resolved NWS grid metadata for a coordinate."""

    office: str
    x: int
    y: int
    grid_url: str
    timezone: str
    city: str = ""
    state: str = ""

    @property
    def zone(self) -> ZoneInfo:
        """The spot's timezone as a :class:`ZoneInfo`."""
        return ZoneInfo(self.timezone)


def parse_duration(text: str) -> dt.timedelta:
    """Parse an ISO-8601 duration such as ``PT4H`` or ``P1DT2H``.

    Only the calendar-independent components (days and below) are accepted,
    which is all the NWS grid uses.

    Raises:
        ValueError: if the string is not a supported duration.
    """
    match = _DURATION_RE.match(text.strip())
    if not match or not any(match.groupdict().values()):
        raise ValueError(f"unsupported ISO-8601 duration: {text!r}")
    parts = {k: float(v) for k, v in match.groupdict().items() if v is not None}
    return dt.timedelta(
        days=parts.get("days", 0.0),
        hours=parts.get("hours", 0.0),
        minutes=parts.get("minutes", 0.0),
        seconds=parts.get("seconds", 0.0),
    )


def parse_interval(text: str) -> tuple[dt.datetime, dt.timedelta]:
    """Split a ``<timestamp>/<duration>`` valid-time into its two halves.

    Raises:
        ValueError: if the interval is malformed.
    """
    start_text, _, duration_text = text.partition("/")
    if not duration_text:
        raise ValueError(f"valid time has no duration: {text!r}")
    start = dt.datetime.fromisoformat(start_text)
    if start.tzinfo is None:
        start = start.replace(tzinfo=dt.UTC)
    return start, parse_duration(duration_text)


def expand_series(
    element: Mapping[str, Any] | None,
    *,
    tz: dt.tzinfo,
) -> dict[dt.datetime, float]:
    """Expand one grid element onto an hourly index in the spot's timezone.

    An entry covering ``PT4H`` becomes four identical hourly values, which
    is exactly what the NWS text products do implicitly when they say
    "this afternoon".

    Raises:
        UnsupportedUnit: if the element declares an unknown unit of measure.
    """
    if not element:
        return {}

    uom = element.get("uom")
    try:
        convert = UNIT_CONVERTERS[uom]
    except KeyError:
        raise UnsupportedUnit(f"unknown unit of measure {uom!r} in NWS grid") from None

    series: dict[dt.datetime, float] = {}
    for entry in element.get("values", ()):
        value = entry.get("value")
        if value is None:
            continue
        try:
            start, duration = parse_interval(str(entry.get("validTime", "")))
        except ValueError:
            continue
        converted = convert(float(value))
        hours = max(1, int(duration.total_seconds() // 3600))
        local_start = start.astimezone(tz).replace(minute=0, second=0, microsecond=0)
        for offset in range(hours):
            series[local_start + dt.timedelta(hours=offset)] = converted
    return series


def weather_phrase(values: Iterable[Mapping[str, Any]]) -> str | None:
    """Turn the NWS weather element into a readable phrase.

    ``{"coverage": "slight_chance", "weather": "rain_showers"}`` becomes
    ``slight chance rain showers``.
    """
    for value in values:
        weather = value.get("weather")
        if not weather:
            continue
        words = [
            str(part).replace("_", " ")
            for part in (value.get("coverage"), value.get("intensity"), weather)
            if part and str(part) != "moderate"
        ]
        return " ".join(words)
    return None


def _weather_series(element: Mapping[str, Any] | None, *, tz: dt.tzinfo) -> dict[dt.datetime, str]:
    if not element:
        return {}
    series: dict[dt.datetime, str] = {}
    for entry in element.get("values", ()):
        phrase = weather_phrase(entry.get("value") or ())
        if not phrase:
            continue
        try:
            start, duration = parse_interval(str(entry.get("validTime", "")))
        except ValueError:
            continue
        hours = max(1, int(duration.total_seconds() // 3600))
        local_start = start.astimezone(tz).replace(minute=0, second=0, microsecond=0)
        for offset in range(hours):
            series[local_start + dt.timedelta(hours=offset)] = phrase
    return series


def build_hours(properties: Mapping[str, Any], *, tz: dt.tzinfo) -> list[Hour]:
    """Assemble hourly conditions from a ``/gridpoints`` payload.

    Wind speed is the spine of the record: an hour with no wind forecast
    cannot be scored, so it is dropped rather than guessed at.
    """
    wind = expand_series(properties.get("windSpeed"), tz=tz)
    if not wind:
        raise NwsError("grid response contains no wind speed series")

    gust = expand_series(properties.get("windGust"), tz=tz)
    direction = expand_series(properties.get("windDirection"), tz=tz)
    waves = expand_series(properties.get("waveHeight"), tz=tz)
    temp = expand_series(properties.get("temperature"), tz=tz)
    feels = expand_series(properties.get("apparentTemperature"), tz=tz)
    precip = expand_series(properties.get("probabilityOfPrecipitation"), tz=tz)
    thunder = expand_series(properties.get("probabilityOfThunder"), tz=tz)
    sky = expand_series(properties.get("skyCover"), tz=tz)
    weather = _weather_series(properties.get("weather"), tz=tz)

    hours: list[Hour] = []
    for when in sorted(wind):
        hours.append(
            Hour(
                time=when,
                wind_kt=round(wind[when], 1),
                gust_kt=_rounded(gust.get(when), 1),
                wind_dir_deg=direction.get(when),
                wave_ft=_rounded(waves.get(when), 1),
                temp_f=_rounded(temp.get(when), 1),
                feels_like_f=_rounded(feels.get(when), 1),
                precip_pct=precip.get(when),
                thunder_pct=thunder.get(when),
                sky_pct=sky.get(when),
                weather=weather.get(when),
            )
        )
    return hours


def _rounded(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


def _parse_time(raw: Any) -> dt.datetime | None:
    if not raw:
        return None
    try:
        return dt.datetime.fromisoformat(str(raw))
    except ValueError:
        return None


class NwsClient:
    """Typed access to the handful of NWS endpoints this tool needs."""

    def __init__(self, fetcher: Fetcher, *, base_url: str = NWS_API) -> None:
        self.fetcher = fetcher
        self.base_url = base_url.rstrip("/")

    def point(self, lat: float, lon: float) -> GridPoint:
        """Resolve a coordinate to its forecast grid and timezone.

        Raises:
            NwsError: if the response lacks the expected properties.
        """
        payload = self.fetcher.get_json(f"{self.base_url}/points/{lat:.4f},{lon:.4f}", ttl=POINT_TTL)
        props = (payload or {}).get("properties") or {}
        grid_url = props.get("forecastGridData")
        timezone = props.get("timeZone")
        if not grid_url or not timezone:
            raise NwsError(f"point metadata for ({lat}, {lon}) is missing grid or timezone")
        location = ((props.get("relativeLocation") or {}).get("properties")) or {}
        return GridPoint(
            office=str(props.get("gridId", "")),
            x=int(props.get("gridX", 0)),
            y=int(props.get("gridY", 0)),
            grid_url=str(grid_url),
            timezone=str(timezone),
            city=str(location.get("city", "")),
            state=str(location.get("state", "")),
        )

    def hours(self, grid: GridPoint) -> list[Hour]:
        """Fetch and normalize the hourly grid for a resolved point.

        Raises:
            NwsError: if the grid payload has no usable wind series.
        """
        payload = self.fetcher.get_json(grid.grid_url, ttl=GRID_TTL)
        properties = (payload or {}).get("properties")
        if not properties:
            raise NwsError(f"grid response for {grid.office} {grid.x},{grid.y} has no properties")
        return build_hours(properties, tz=grid.zone)

    def hazards(self, lat: float, lon: float, *, tz: dt.tzinfo | None = None) -> list[Hazard]:
        """Active watches, warnings and advisories covering a coordinate.

        Network or parse failures return an empty list: a missing advisory
        should degrade the report, not abort it.
        """
        url = f"{self.base_url}/alerts/active?point={lat:.4f},{lon:.4f}"
        try:
            payload = self.fetcher.get_json(url, ttl=ALERT_TTL)
        except Exception:
            return []

        hazards: list[Hazard] = []
        for feature in (payload or {}).get("features", ()):
            props = feature.get("properties") or {}
            if str(props.get("status", "")).lower() in _IGNORED_ALERT_STATUSES:
                continue
            event = str(props.get("event", "")).strip()
            if not event:
                continue
            onset = _parse_time(props.get("onset") or props.get("effective"))
            ends = _parse_time(props.get("ends") or props.get("expires"))
            if tz is not None:
                onset = onset.astimezone(tz) if onset else None
                ends = ends.astimezone(tz) if ends else None
            hazards.append(
                Hazard(
                    event=event,
                    severity=str(props.get("severity", "Unknown")),
                    headline=str(props.get("headline") or props.get("description") or event).strip(),
                    onset=onset,
                    ends=ends,
                )
            )
        return hazards

    def forecast(self, spot: Spot) -> tuple[GridPoint, list[Hour], list[Hazard]]:
        """One call for everything a report needs from NWS."""
        grid = self.point(spot.lat, spot.lon)
        if spot.timezone:
            grid = GridPoint(
                office=grid.office,
                x=grid.x,
                y=grid.y,
                grid_url=grid.grid_url,
                timezone=spot.timezone,
                city=grid.city,
                state=grid.state,
            )
        return grid, self.hours(grid), self.hazards(spot.lat, spot.lon, tz=grid.zone)
