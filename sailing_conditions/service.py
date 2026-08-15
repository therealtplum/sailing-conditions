"""The assembly line: sources in, scored :class:`Report` out.

This is the only module that knows the whole story — which sources exist,
in what order they are consulted, and how their output becomes a report.
Everything it depends on is injected, so a report can be built from live
NWS data or from fixtures with the same code path.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .models import DayOutlook, Hour, Observation, Report, ScoredHour, Spot
from .profiles import BoatProfile
from .scoring import score_hour
from .settings import Settings
from .sources.http import DiskCache, Fetcher, HttpClient
from .sources.ndbc import NdbcClient
from .sources.nws import NwsClient
from .sun import is_daylight, sun_times
from .windows import DEFAULT_MIN_HOURS, DEFAULT_MIN_SCORE, find_windows

#: How far the forecast-versus-buoy delta may drift before it is called out.
DIVERGENCE_KT = 6.0


@dataclass(frozen=True, slots=True)
class Forecaster:
    """Builds scored reports for spots."""

    nws: NwsClient
    ndbc: NdbcClient | None = None

    def report(
        self,
        spot: Spot,
        profile: BoatProfile,
        *,
        days: int = 2,
        start: dt.date | None = None,
        min_score: float = DEFAULT_MIN_SCORE,
        min_hours: int = DEFAULT_MIN_HOURS,
        live: bool = True,
        now: dt.datetime | None = None,
    ) -> Report:
        """Fetch, score and assemble a report for one spot.

        Args:
            spot: Where to sail.
            profile: Which boat the score is for.
            days: Number of local dates to include, starting at ``start``.
            start: First local date; defaults to today in the spot's zone.
            min_score: Threshold an hour must clear to join a window.
            min_hours: Shortest window worth reporting.
            live: Whether to consult the spot's buoy for current conditions.
            now: Injectable clock, for tests and reproducible fixtures.

        Returns:
            A fully populated :class:`~sailing_conditions.models.Report`.
        """
        grid, hours, hazards = self.nws.forecast(spot)
        tz = grid.zone
        current = (now or dt.datetime.now(dt.UTC)).astimezone(tz)
        first_day = start or current.date()
        wanted = {first_day + dt.timedelta(days=offset) for offset in range(max(1, days))}

        notes: list[str] = []
        observation = None
        if live and self.ndbc is not None and spot.buoy:
            observation = self.ndbc.latest(spot.buoy)
            notes.extend(self._observation_notes(spot, observation, hours, current))

        if all(hour.wave_ft is None for hour in hours):
            notes.append("No wave grid at this spot — the score runs on wind, sky and comfort alone.")

        # The grid still carries hours that have already happened. They are not
        # a forecast, and a window search over them would cheerfully tell you
        # to go sailing this morning — at four in the afternoon.
        first_hour = current.replace(minute=0, second=0, microsecond=0)

        by_date: defaultdict[dt.date, list[ScoredHour]] = defaultdict(list)
        for hour in hours:
            if hour.time.date() not in wanted or hour.time < first_hour:
                continue
            by_date[hour.time.date()].append(ScoredHour(hour, score_hour(hour, profile, hazards)))

        outlooks: list[DayOutlook] = []
        for day in sorted(by_date):
            sun = sun_times(spot.lat, spot.lon, day, tz)
            scored = tuple(
                ScoredHour(item.hour, item.score, daylight=is_daylight(item.time, sun))
                for item in sorted(by_date[day], key=lambda item: item.time)
            )
            windows = find_windows(scored, min_score=min_score, min_hours=min_hours)
            outlooks.append(DayOutlook(date=day, sun=sun, hours=scored, windows=windows))

        if not outlooks:
            notes.append("The NWS grid returned no hours for the requested dates.")

        return Report(
            spot=spot,
            profile_key=profile.key,
            generated_at=current,
            timezone=grid.timezone,
            days=tuple(outlooks),
            hazards=tuple(hazards),
            observation=observation,
            notes=tuple(notes),
        )

    def reports(
        self,
        spots: Sequence[Spot],
        profile: BoatProfile,
        *,
        days: int = 2,
        start: dt.date | None = None,
        min_score: float = DEFAULT_MIN_SCORE,
        min_hours: int = DEFAULT_MIN_HOURS,
        live: bool = True,
        now: dt.datetime | None = None,
    ) -> list[Report]:
        """Build reports for several spots, degrading gracefully on failure.

        A single unreachable grid should not cost you the other five spots;
        the failure is recorded as a note on an otherwise empty report.
        """
        out: list[Report] = []
        for spot in spots:
            try:
                out.append(
                    self.report(
                        spot,
                        profile,
                        days=days,
                        start=start,
                        min_score=min_score,
                        min_hours=min_hours,
                        live=live,
                        now=now,
                    )
                )
            except Exception as exc:
                out.append(
                    Report(
                        spot=spot,
                        profile_key=profile.key,
                        generated_at=now or dt.datetime.now(dt.UTC),
                        timezone="UTC",
                        notes=(f"Forecast unavailable: {exc}",),
                    )
                )
        return out

    @staticmethod
    def _observation_notes(
        spot: Spot,
        observation: Observation | None,
        hours: Sequence[Hour],
        current: dt.datetime,
    ) -> list[str]:
        """Flag a dead buoy, a stale reading, or a model that has lost the plot."""
        if observation is None:
            return [f"Buoy {spot.buoy} is not reporting — using forecast only."]

        notes: list[str] = []
        age_minutes = observation.age.total_seconds() / 60
        if age_minutes > 120:
            notes.append(f"Buoy {observation.station} last reported {age_minutes / 60:.1f} h ago.")

        if observation.wind_kt is None:
            return notes

        this_hour = current.replace(minute=0, second=0, microsecond=0)
        forecast_now = next((h for h in hours if h.time == this_hour), None)
        if forecast_now is None:
            return notes

        delta = observation.wind_kt - forecast_now.wind_kt
        if abs(delta) >= DIVERGENCE_KT:
            notes.append(
                f"Buoy {observation.station} reads {observation.wind_kt:.0f} kt against a "
                f"{forecast_now.wind_kt:.0f} kt forecast ({delta:+.0f} kt) — trust the water."
            )
        return notes


def build_fetcher(settings: Settings, *, use_cache: bool = True) -> Fetcher:
    """Construct the HTTP client described by ``settings``."""
    cache = None
    if use_cache and settings.cache_dir is not None:
        cache = DiskCache(Path(settings.cache_dir))
    return HttpClient(settings.user_agent, cache=cache)


def build_forecaster(
    settings: Settings,
    *,
    fetcher: Fetcher | None = None,
    use_cache: bool = True,
    live: bool = True,
) -> Forecaster:
    """Wire up a forecaster from settings, or around an injected fetcher."""
    fetcher = fetcher or build_fetcher(settings, use_cache=use_cache)
    return Forecaster(nws=NwsClient(fetcher), ndbc=NdbcClient(fetcher) if live else None)
