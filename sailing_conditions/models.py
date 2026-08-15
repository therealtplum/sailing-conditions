"""Domain model.

Every type here is a frozen dataclass with no I/O and no formatting logic.
The data flows in one direction::

    Hour  ──score()──▶  ScoredHour  ──find_windows()──▶  Window
                                    ──group by date───▶  DayOutlook  ──▶  Report

Keeping the model inert is what lets the scoring rules be unit-tested
without a network, and lets the renderers stay dumb.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from enum import Enum

from .timefmt import hour_label
from .units import beaufort, beaufort_label, compass, gust_ratio


class Verdict(str, Enum):
    """Plain-language bucket for a score. Ordered worst to best."""

    NO_GO = "no_go"
    POOR = "poor"
    MARGINAL = "marginal"
    GOOD = "good"
    EPIC = "epic"

    @property
    def label(self) -> str:
        """Short label for terminal and message output."""
        return {
            Verdict.EPIC: "SEND IT",
            Verdict.GOOD: "GO SAILING",
            Verdict.MARGINAL: "MARGINAL",
            Verdict.POOR: "STAY IN",
            Verdict.NO_GO: "NO-GO",
        }[self]

    @property
    def color(self) -> str:
        """Rich style name used by the console renderer."""
        return {
            Verdict.EPIC: "bold bright_green",
            Verdict.GOOD: "green",
            Verdict.MARGINAL: "yellow",
            Verdict.POOR: "dark_orange",
            Verdict.NO_GO: "bold red",
        }[self]

    @classmethod
    def from_score(cls, score: float, *, vetoed: bool = False) -> Verdict:
        """Map a 0-10 score onto a verdict; any hard veto forces ``NO_GO``."""
        if vetoed:
            return cls.NO_GO
        if score >= 8.5:
            return cls.EPIC
        if score >= 7.0:
            return cls.GOOD
        if score >= 5.0:
            return cls.MARGINAL
        if score >= 2.5:
            return cls.POOR
        return cls.NO_GO


@dataclass(frozen=True, slots=True)
class Spot:
    """A place you can go sailing."""

    key: str
    name: str
    lat: float
    lon: float
    region: str = ""
    blurb: str = ""
    buoy: str | None = None
    """NDBC station ID used for live observations, if one is nearby."""
    timezone: str | None = None
    """IANA zone. Left ``None`` for built-ins: NWS reports the authoritative one."""
    tags: tuple[str, ...] = ()

    @property
    def title(self) -> str:
        """``Belmont Harbor, Chicago IL`` style heading."""
        return f"{self.name}, {self.region}" if self.region else self.name


@dataclass(frozen=True, slots=True)
class Hour:
    """Forecast conditions valid for one hour at one spot.

    Every field except ``time`` and ``wind_kt`` is optional: NWS grids omit
    wave height inland, thunder probability beyond a few days out, and so on.
    Scoring treats a missing factor as *unknown*, never as *zero*.
    """

    time: dt.datetime
    """Timezone-aware, in the spot's local zone."""
    wind_kt: float
    gust_kt: float | None = None
    wind_dir_deg: float | None = None
    wave_ft: float | None = None
    temp_f: float | None = None
    feels_like_f: float | None = None
    precip_pct: float | None = None
    thunder_pct: float | None = None
    sky_pct: float | None = None
    """Cloud cover, 0 (clear) to 100 (overcast)."""
    weather: str | None = None
    """Short phrase from the NWS weather grid, e.g. ``chance rain showers``."""

    @property
    def wind_dir(self) -> str | None:
        """16-point compass direction, or ``None`` when the wind is calm."""
        return compass(self.wind_dir_deg)

    @property
    def gust_ratio(self) -> float | None:
        """Gust divided by sustained wind, or ``None`` if not meaningful."""
        return gust_ratio(self.wind_kt, self.gust_kt)

    @property
    def beaufort(self) -> int:
        """Beaufort force for the sustained wind."""
        return beaufort(self.wind_kt)

    @property
    def wind_phrase(self) -> str:
        """``SW 12 kt g18`` — the way a sailor would say it."""
        direction = f"{self.wind_dir} " if self.wind_dir else ""
        gust = f" g{self.gust_kt:.0f}" if self.gust_kt and self.gust_kt > self.wind_kt + 2 else ""
        return f"{direction}{self.wind_kt:.0f} kt{gust}"

    @property
    def sky_phrase(self) -> str:
        """Cloud cover expressed the way a forecast would."""
        if self.weather:
            return self.weather
        if self.sky_pct is None:
            return "—"
        if self.sky_pct < 12:
            return "clear"
        if self.sky_pct < 38:
            return "mostly sunny"
        if self.sky_pct < 70:
            return "partly cloudy"
        if self.sky_pct < 88:
            return "mostly cloudy"
        return "overcast"

    def describe(self) -> str:
        """One-line summary used in alerts and fallback text."""
        parts = [self.wind_phrase, f"{beaufort_label(self.wind_kt)}"]
        if self.wave_ft is not None:
            parts.append(f"{self.wave_ft:.1f} ft seas")
        if self.feels_like_f is not None:
            parts.append(f"{self.feels_like_f:.0f}°F")
        parts.append(self.sky_phrase)
        return ", ".join(parts)


@dataclass(frozen=True, slots=True)
class Factor:
    """One scored component of an hour, with the arithmetic left visible.

    ``score`` is the normalized 0-1 quality of this component and ``weight``
    is its exponent in the weighted geometric mean. ``note`` explains the
    number in English so ``--explain`` never has to reverse-engineer it.
    """

    name: str
    score: float
    weight: float
    note: str


@dataclass(frozen=True, slots=True)
class Veto:
    """A hard gate that overrides the weighted score.

    Vetoes exist because sailing risk is not a smooth trade-off: no amount
    of sunshine offsets a thunderstorm overhead.
    """

    reason: str
    cap: float
    """Highest score the hour may still receive."""
    hard: bool = True
    """``True`` forces a ``NO_GO`` verdict regardless of the capped score."""


@dataclass(frozen=True, slots=True)
class Score:
    """The result of scoring one hour."""

    value: float
    verdict: Verdict
    factors: tuple[Factor, ...] = ()
    vetoes: tuple[Veto, ...] = ()

    @property
    def vetoed(self) -> bool:
        """Whether any hard veto applied."""
        return any(v.hard for v in self.vetoes)

    @property
    def limiting_factor(self) -> Factor | None:
        """The component dragging the score down the most.

        Ranked by each factor's actual contribution to the weighted geometric
        mean — ``weight × log(score)``, the term it adds to the sum. So a
        heavily weighted mediocre factor outranks a lightly weighted terrible
        one, which is what a skipper actually cares about: light wind ruins
        the day, an overcast sky does not.
        """
        if not self.factors:
            return None
        return min(self.factors, key=lambda f: f.weight * math.log(max(f.score, 1e-3)))


@dataclass(frozen=True, slots=True)
class ScoredHour:
    """An hour plus its score and whether the sun is up."""

    hour: Hour
    score: Score
    daylight: bool = True

    @property
    def time(self) -> dt.datetime:
        """Convenience passthrough to the hour's local timestamp."""
        return self.hour.time

    @property
    def value(self) -> float:
        """Convenience passthrough to the numeric score."""
        return self.score.value


@dataclass(frozen=True, slots=True)
class Window:
    """A contiguous run of hours that clear the sailing threshold."""

    hours: tuple[ScoredHour, ...]

    @property
    def start(self) -> dt.datetime:
        """Local start time of the window."""
        return self.hours[0].time

    @property
    def end(self) -> dt.datetime:
        """Local end time — one hour past the last qualifying hour."""
        return self.hours[-1].time + dt.timedelta(hours=1)

    @property
    def length_hours(self) -> int:
        """Duration in whole hours."""
        return len(self.hours)

    @property
    def mean_score(self) -> float:
        """Average score across the window."""
        return sum(h.value for h in self.hours) / len(self.hours)

    @property
    def peak(self) -> ScoredHour:
        """The single best hour in the window."""
        return max(self.hours, key=lambda h: h.value)

    @property
    def verdict(self) -> Verdict:
        """Verdict for the window as a whole."""
        return Verdict.from_score(self.mean_score)

    def describe(self) -> str:
        """``10am–2pm`` style range."""
        return f"{hour_label(self.start)}–{hour_label(self.end)}"


@dataclass(frozen=True, slots=True)
class SunTimes:
    """Solar events for one date at one spot, in local time."""

    date: dt.date
    sunrise: dt.datetime | None
    sunset: dt.datetime | None
    solar_noon: dt.datetime | None
    daylight_hours: float

    @property
    def polar_day(self) -> bool:
        """True when the sun never sets on this date."""
        return self.sunrise is None and self.daylight_hours >= 24

    @property
    def polar_night(self) -> bool:
        """True when the sun never rises on this date."""
        return self.sunrise is None and self.daylight_hours <= 0


@dataclass(frozen=True, slots=True)
class Hazard:
    """An active NWS watch, warning or advisory covering the spot."""

    event: str
    severity: str
    headline: str
    onset: dt.datetime | None = None
    ends: dt.datetime | None = None

    def covers(self, when: dt.datetime) -> bool:
        """Whether this hazard is in force at ``when``."""
        if self.onset and when < self.onset:
            return False
        return not (self.ends and when >= self.ends)


@dataclass(frozen=True, slots=True)
class Observation:
    """A live buoy report — what is actually happening right now."""

    station: str
    time: dt.datetime
    wind_kt: float | None = None
    gust_kt: float | None = None
    wind_dir_deg: float | None = None
    wave_ft: float | None = None
    wave_period_s: float | None = None
    air_temp_f: float | None = None
    water_temp_f: float | None = None

    @property
    def age(self) -> dt.timedelta:
        """How stale this observation is."""
        return dt.datetime.now(dt.UTC) - self.time

    @property
    def wind_dir(self) -> str | None:
        """16-point compass direction of the observed wind."""
        return compass(self.wind_dir_deg)

    def describe(self) -> str:
        """One-line summary for the console header."""
        bits = []
        if self.wind_kt is not None:
            direction = f"{self.wind_dir} " if self.wind_dir else ""
            gust = f" g{self.gust_kt:.0f}" if self.gust_kt else ""
            bits.append(f"{direction}{self.wind_kt:.0f} kt{gust}")
        if self.wave_ft is not None:
            bits.append(f"{self.wave_ft:.1f} ft")
        if self.water_temp_f is not None:
            bits.append(f"{self.water_temp_f:.0f}°F water")
        return ", ".join(bits) if bits else "no data"


@dataclass(frozen=True, slots=True)
class DayOutlook:
    """Everything known about one local date at one spot."""

    date: dt.date
    sun: SunTimes
    hours: tuple[ScoredHour, ...]
    windows: tuple[Window, ...] = ()

    @property
    def best_window(self) -> Window | None:
        """The highest-scoring window of the day, if any hour qualified."""
        return self.windows[0] if self.windows else None

    @property
    def daylight_hours(self) -> tuple[ScoredHour, ...]:
        """Only the hours between sunrise and sunset."""
        return tuple(h for h in self.hours if h.daylight)

    @property
    def peak(self) -> ScoredHour | None:
        """Best single daylight hour, falling back to the best hour overall."""
        pool = self.daylight_hours or self.hours
        return max(pool, key=lambda h: h.value) if pool else None

    @property
    def score(self) -> float:
        """Headline score for the day.

        The mean of the best three daylight hours: a day with one glorious
        afternoon should not be averaged into mediocrity by a dead morning,
        but a single flukey hour should not carry the day either.
        """
        pool = self.daylight_hours or self.hours
        if not pool:
            return 0.0
        top = sorted((h.value for h in pool), reverse=True)[:3]
        return sum(top) / len(top)

    @property
    def verdict(self) -> Verdict:
        """Verdict derived from the headline score."""
        return Verdict.from_score(self.score)


@dataclass(frozen=True, slots=True)
class Report:
    """A scored forecast for one spot, ready to render or notify on."""

    spot: Spot
    profile_key: str
    generated_at: dt.datetime
    timezone: str
    days: tuple[DayOutlook, ...] = ()
    hazards: tuple[Hazard, ...] = ()
    observation: Observation | None = None
    notes: tuple[str, ...] = field(default=())
    """Non-fatal data-quality remarks, e.g. a buoy that is offline."""

    @property
    def today(self) -> DayOutlook | None:
        """The first day in the report."""
        return self.days[0] if self.days else None

    @property
    def best_day(self) -> DayOutlook | None:
        """The highest-scoring day in the report."""
        return max(self.days, key=lambda d: d.score) if self.days else None

    def headline(self) -> str:
        """One-sentence summary — the thing worth pushing to a phone."""
        day = self.today
        if day is None:
            return f"{self.spot.name}: no forecast data."
        window = day.best_window
        head = f"{self.spot.name} {day.score:.1f}/10 — {day.verdict.label}"
        if window:
            peak = window.peak.hour
            return f"{head}. Best {window.describe()}, {peak.wind_phrase}."
        if day.peak:
            return f"{head}. Peak {day.peak.hour.wind_phrase} at {hour_label(day.peak.time)}."
        return head
