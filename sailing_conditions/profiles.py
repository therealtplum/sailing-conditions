"""Boat profiles — the tunable half of the scoring model.

A 22 kt breeze with 4 ft chop is a great day on a keelboat, a survival
exercise in a Laser, and a canceled lesson for a beginner. The scoring
rules in :mod:`sailing_conditions.scoring` are identical for everyone; the
*constants* live here, so "what counts as good" is data, not code.

Add your own in ``~/.config/sailing-conditions/config.toml``::

    [profiles.my_j24]
    name = "My J/24"
    wind = { min = 6, ideal_lo = 10, ideal_hi = 20, max = 28 }
    wave_ok_ft = 3.0
    wave_max_ft = 6.0
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

DEFAULT_PROFILE = "keelboat"

#: Relative exponents in the weighted geometric mean. Wind dominates by
#: design: it is the only factor without which there is no sailing at all.
DEFAULT_WEIGHTS: Mapping[str, float] = {
    "wind": 3.0,
    "sea": 1.5,
    "gust": 1.0,
    "precip": 1.0,
    "comfort": 0.8,
    "sky": 0.4,
}


@dataclass(frozen=True, slots=True)
class WindBand:
    """Four knots that define a boat's response curve to wind speed.

    ``min`` and ``max`` are the zero-fun bounds; between ``ideal_lo`` and
    ``ideal_hi`` the wind factor is a flat 1.0. The curve ramps linearly
    across the two shoulders — no cliffs, so a 1 kt forecast revision never
    swings the verdict by three points.
    """

    min: float
    ideal_lo: float
    ideal_hi: float
    max: float

    def __post_init__(self) -> None:
        if not self.min <= self.ideal_lo <= self.ideal_hi <= self.max:
            raise ValueError(
                f"wind band must be non-decreasing, got "
                f"{self.min}/{self.ideal_lo}/{self.ideal_hi}/{self.max}"
            )

    def describe(self) -> str:
        """``6-10-20-28 kt`` style summary for ``sail profiles``."""
        return f"{self.min:g}–{self.ideal_lo:g}–{self.ideal_hi:g}–{self.max:g} kt"


@dataclass(frozen=True, slots=True)
class BoatProfile:
    """Everything the scorer needs to know about a boat and her skipper."""

    key: str
    name: str
    summary: str
    wind: WindBand

    # Gusts are scored on the ratio to sustained wind, not absolute speed:
    # 12 kt gusting 30 is a harder day than a steady 25.
    gust_ratio_ok: float = 1.35
    gust_ratio_max: float = 2.0

    wave_ok_ft: float = 2.5
    wave_max_ft: float = 5.0
    """Comfort limits for a day sail, not survival limits. A 35-footer will
    live through 8 ft seas; nobody aboard will enjoy the afternoon."""

    thunder_veto_pct: float = 30.0
    """Probability of thunder at which the hour becomes a hard no-go."""

    comfort_f: tuple[float, float] = (62.0, 88.0)
    """Apparent-temperature band where nobody is thinking about the weather."""
    comfort_min_f: float = 38.0
    comfort_max_f: float = 102.0

    weights: Mapping[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))

    def weight(self, factor: str) -> float:
        """Weight for a named factor, falling back to the default table."""
        return float(self.weights.get(factor, DEFAULT_WEIGHTS.get(factor, 1.0)))

    def with_overrides(self, **overrides: Any) -> BoatProfile:
        """Return a copy with individual fields replaced."""
        return replace(self, **overrides)


def _profile(
    key: str,
    name: str,
    summary: str,
    band: tuple[float, float, float, float],
    **kwargs: Any,
) -> BoatProfile:
    return BoatProfile(key=key, name=name, summary=summary, wind=WindBand(*band), **kwargs)


#: Built-in profiles. Numbers are conventional rules of thumb, not gospel —
#: they are here to be argued with and overridden.
BUILTIN_PROFILES: dict[str, BoatProfile] = {
    "keelboat": _profile(
        "keelboat",
        "Keelboat",
        "25-40 ft cruiser-racer. Happy in a fresh breeze, tolerant of chop.",
        (5, 10, 20, 30),
        wave_ok_ft=3.0,
        wave_max_ft=5.5,
    ),
    "dinghy": _profile(
        "dinghy",
        "Dinghy",
        "Laser, 420, Sunfish. Planes early, capsizes late, hates slop.",
        (4, 8, 16, 24),
        gust_ratio_ok=1.25,
        gust_ratio_max=1.8,
        wave_ok_ft=1.5,
        wave_max_ft=3.5,
        comfort_f=(66.0, 90.0),
        comfort_min_f=48.0,
    ),
    "catamaran": _profile(
        "catamaran",
        "Catamaran",
        "Beach cat or sport cat. Wants pressure and flat water.",
        (6, 11, 22, 32),
        gust_ratio_ok=1.3,
        wave_ok_ft=2.0,
        wave_max_ft=4.0,
    ),
    "cruiser": _profile(
        "cruiser",
        "Cruiser",
        "Family day sail. Comfort first — nobody wants the rail down.",
        (5, 9, 16, 24),
        gust_ratio_ok=1.3,
        gust_ratio_max=1.7,
        wave_ok_ft=2.0,
        wave_max_ft=4.0,
        thunder_veto_pct=20.0,
        comfort_f=(66.0, 88.0),
        comfort_min_f=50.0,
    ),
    "beginner": _profile(
        "beginner",
        "Beginner",
        "First season, or teaching someone who is. Narrow band, low drama.",
        (3, 6, 12, 18),
        gust_ratio_ok=1.2,
        gust_ratio_max=1.6,
        wave_ok_ft=1.0,
        wave_max_ft=2.5,
        thunder_veto_pct=15.0,
        comfort_f=(68.0, 88.0),
        comfort_min_f=55.0,
        weights={**DEFAULT_WEIGHTS, "gust": 1.6, "sea": 2.0},
    ),
    "heavy_air": _profile(
        "heavy_air",
        "Heavy air",
        "You own a storm jib and you enjoy using it.",
        (10, 16, 28, 40),
        gust_ratio_ok=1.5,
        gust_ratio_max=2.3,
        wave_ok_ft=4.5,
        wave_max_ft=9.0,
        comfort_f=(50.0, 88.0),
        comfort_min_f=32.0,
        weights={**DEFAULT_WEIGHTS, "sky": 0.2, "comfort": 0.4},
    ),
    "foiler": _profile(
        "foiler",
        "Foiler",
        "Needs enough breeze to get up, flat water to stay up.",
        (8, 12, 22, 30),
        gust_ratio_ok=1.3,
        wave_ok_ft=1.2,
        wave_max_ft=3.0,
        weights={**DEFAULT_WEIGHTS, "sea": 2.2},
    ),
}


def get_profile(key: str, extra: Mapping[str, BoatProfile] | None = None) -> BoatProfile:
    """Look up a profile by key, searching user profiles first.

    Raises:
        KeyError: if the key is unknown, with the valid keys in the message.
    """
    if extra and key in extra:
        return extra[key]
    if key in BUILTIN_PROFILES:
        return BUILTIN_PROFILES[key]
    known = sorted({*BUILTIN_PROFILES, *(extra or {})})
    raise KeyError(f"unknown profile {key!r}; try one of: {', '.join(known)}")


def profile_from_mapping(key: str, data: Mapping[str, Any]) -> BoatProfile:
    """Build a profile from parsed TOML.

    Unspecified fields inherit from the built-in named by ``extends``
    (default ``keelboat``), so a user profile can be three lines long.
    """
    base = BUILTIN_PROFILES[str(data.get("extends", DEFAULT_PROFILE))]
    wind = data.get("wind")
    band = base.wind
    if isinstance(wind, Mapping):
        band = WindBand(
            min=float(wind.get("min", base.wind.min)),
            ideal_lo=float(wind.get("ideal_lo", base.wind.ideal_lo)),
            ideal_hi=float(wind.get("ideal_hi", base.wind.ideal_hi)),
            max=float(wind.get("max", base.wind.max)),
        )
    comfort = data.get("comfort_f", base.comfort_f)
    weights = {**base.weights, **dict(data.get("weights", {}))}
    return BoatProfile(
        key=key,
        name=str(data.get("name", key.replace("_", " ").title())),
        summary=str(data.get("summary", base.summary)),
        wind=band,
        gust_ratio_ok=float(data.get("gust_ratio_ok", base.gust_ratio_ok)),
        gust_ratio_max=float(data.get("gust_ratio_max", base.gust_ratio_max)),
        wave_ok_ft=float(data.get("wave_ok_ft", base.wave_ok_ft)),
        wave_max_ft=float(data.get("wave_max_ft", base.wave_max_ft)),
        thunder_veto_pct=float(data.get("thunder_veto_pct", base.thunder_veto_pct)),
        comfort_f=(float(comfort[0]), float(comfort[1])),
        comfort_min_f=float(data.get("comfort_min_f", base.comfort_min_f)),
        comfort_max_f=float(data.get("comfort_max_f", base.comfort_max_f)),
        weights=weights,
    )
