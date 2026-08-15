"""National Data Buoy Center client — what the water is doing *right now*.

A forecast grid is a model output; a buoy is a measurement. When a spot has
a station nearby, the live observation is worth more than any forecast for
the current hour, and it is the fastest way to notice that a model has lost
the plot ("forecast says 8 kt, the crib says 19").

The realtime2 format is a fixed-width-ish table, newest row first, with
``MM`` for missing values::

    #YY  MM DD hh mm WDIR WSPD GST  WVHT   DPD   APD MWD   PRES  ATMP  WTMP
    2026 08 15 08 50 190  4.1  4.1    MM    MM    MM  MM     MM  23.3    MM

Sensors report on different cadences, so the newest row often has gaps that
the row ten minutes earlier fills. Each field is therefore taken from the
most recent row that actually has it, within a bounded lookback.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from ..models import Observation
from ..units import celsius_to_fahrenheit, metres_to_feet, ms_to_knots
from .http import Fetcher

REALTIME_URL = "https://www.ndbc.noaa.gov/data/realtime2/{station}.txt"

#: Buoys report every 10 minutes; a 10-minute cache is plenty.
OBSERVATION_TTL = 10 * 60

#: How many rows back to look when filling a gap (rows are ~10 min apart).
DEFAULT_LOOKBACK_ROWS = 12

MISSING = "MM"


def _value(rows: Sequence[Sequence[str]], index: int | None) -> float | None:
    """First present value for a column, scanning newest row to oldest."""
    if index is None:
        return None
    for row in rows:
        if index >= len(row):
            continue
        raw = row[index]
        if raw == MISSING:
            continue
        try:
            return float(raw)
        except ValueError:
            continue
    return None


def parse_realtime(
    text: str,
    station: str,
    *,
    lookback_rows: int = DEFAULT_LOOKBACK_ROWS,
) -> Observation | None:
    """Parse an NDBC realtime2 table into an :class:`Observation`.

    Returns ``None`` when the table has no data rows or no parseable
    timestamp — a station can be online but reporting nothing.
    """
    header: list[str] = []
    rows: list[list[str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            if not header:
                header = line.lstrip("#").split()
            continue
        rows.append(line.split())

    if not header or not rows:
        return None

    index = {name: position for position, name in enumerate(header)}
    window = rows[:lookback_rows]
    latest = window[0]

    try:
        stamp = dt.datetime(
            year=int(latest[index["YY"]]),
            month=int(latest[index["MM"]]),
            day=int(latest[index["DD"]]),
            hour=int(latest[index["hh"]]),
            minute=int(latest[index["mm"]]),
            tzinfo=dt.UTC,
        )
    except (KeyError, IndexError, ValueError):
        return None

    wind_ms = _value(window, index.get("WSPD"))
    gust_ms = _value(window, index.get("GST"))
    wave_m = _value(window, index.get("WVHT"))
    air_c = _value(window, index.get("ATMP"))
    water_c = _value(window, index.get("WTMP"))

    return Observation(
        station=station.upper(),
        time=stamp,
        wind_kt=None if wind_ms is None else round(ms_to_knots(wind_ms), 1),
        gust_kt=None if gust_ms is None else round(ms_to_knots(gust_ms), 1),
        wind_dir_deg=_value(window, index.get("WDIR")),
        wave_ft=None if wave_m is None else round(metres_to_feet(wave_m), 1),
        wave_period_s=_value(window, index.get("DPD")),
        air_temp_f=None if air_c is None else round(celsius_to_fahrenheit(air_c), 1),
        water_temp_f=None if water_c is None else round(celsius_to_fahrenheit(water_c), 1),
    )


class NdbcClient:
    """Fetches the latest observation for a buoy."""

    def __init__(self, fetcher: Fetcher, *, url_template: str = REALTIME_URL) -> None:
        self.fetcher = fetcher
        self.url_template = url_template

    def latest(self, station: str) -> Observation | None:
        """Latest observation, or ``None`` if the station is unreachable.

        Buoys go offline for maintenance, ice and passing ships. That is a
        footnote on the report, never a failure of it.
        """
        url = self.url_template.format(station=station.upper())
        try:
            text = self.fetcher.get_text(url, ttl=OBSERVATION_TTL)
        except Exception:
            return None
        return parse_realtime(text, station)
