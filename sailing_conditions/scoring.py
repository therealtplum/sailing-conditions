r"""The scoring model.

An hour is scored in two stages.

**1. Weighted geometric mean of continuous factors.** Each factor maps a
physical quantity onto ``[0, 1]`` through a piecewise-linear response curve
whose breakpoints come from the :class:`~sailing_conditions.profiles.BoatProfile`.
The factors combine as

.. math::

    S = 10 \cdot \Bigl(\prod_i f_i^{\,w_i}\Bigr)^{1/\sum_i w_i}

A geometric mean is used rather than an arithmetic one because sailing
quality is *conjunctive*: brilliant sunshine does not compensate for no
wind. With a geometric mean any single bad factor drags the result toward
zero, which is the behavior a sailor expects. Missing data is dropped from
both the product and the weight sum, so an inland spot with no wave grid is
scored on what is known instead of being penalized for what is not.

**2. Hard vetoes.** Some conditions are not trade-offs. Lightning, a Gale
Warning, or wind past the boat's maximum cap the score outright and force a
``NO_GO`` verdict. Vetoes are applied *after* the mean so the underlying
quality stays visible in ``--explain``: "8.7 conditions, capped to 1.0 by a
Special Marine Warning" is more useful than a bare 1.0.

Every factor carries its own English explanation, so the score is never a
black box.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from .models import Factor, Hazard, Hour, Score, Verdict, Veto
from .profiles import BoatProfile
from .units import clamp

#: Factors are floored rather than allowed to hit zero: a true zero would
#: annihilate the product and erase the information in every other factor.
FACTOR_FLOOR = 0.02

#: NWS events that end the conversation.
CRITICAL_EVENTS = frozenset({
    "special marine warning",
    "severe thunderstorm warning",
    "tornado warning",
    "tornado watch",
    "hurricane warning",
    "hurricane force wind warning",
    "tropical storm warning",
    "storm warning",
    "gale warning",
    "squall warning",
    "extreme wind warning",
})

#: NWS events that cap the score but leave the call to the skipper.
CAUTION_EVENTS = frozenset({
    "small craft advisory",
    "marine weather statement",
    "hazardous seas warning",
    "dense fog advisory",
    "wind advisory",
    "high wind warning",
    "severe thunderstorm watch",
    "flood warning",
    "beach hazards statement",
    "rip current statement",
    "heat advisory",
    "excessive heat warning",
    "freeze warning",
    "winter storm warning",
})

CAUTION_CAP = 4.5
CRITICAL_CAP = 1.0


def ramp(x: float, zero_at: float, one_at: float) -> float:
    """Linear ramp from 0 at ``zero_at`` to 1 at ``one_at``, clamped.

    Works in either direction: ``ramp(x, 10, 4)`` falls from 1 to 0 as x
    grows from 4 to 10.
    """
    if zero_at == one_at:
        return 1.0 if x >= one_at else 0.0
    return clamp((x - zero_at) / (one_at - zero_at), 0.0, 1.0)


def plateau(x: float, zero_lo: float, one_lo: float, one_hi: float, zero_hi: float) -> float:
    """Trapezoidal response: 0 outside, 1 across the middle, linear shoulders."""
    if x <= one_lo:
        return ramp(x, zero_lo, one_lo)
    if x >= one_hi:
        return ramp(x, zero_hi, one_hi)
    return 1.0


def rescale(value: float, floor: float) -> float:
    """Compress ``[0, 1]`` into ``[floor, 1]``.

    Used for factors that make a day unpleasant rather than unsailable —
    cold hands should cost points, not veto the sail.
    """
    return floor + (1.0 - floor) * value


def _wind_factor(hour: Hour, profile: BoatProfile) -> Factor:
    band = profile.wind
    score = plateau(hour.wind_kt, band.min, band.ideal_lo, band.ideal_hi, band.max)
    kt = hour.wind_kt
    if kt < band.min:
        note = f"glassy — {kt:.0f} kt is under the {band.min:g} kt floor"
    elif kt < band.ideal_lo:
        note = f"light — {kt:.0f} kt, building toward the {band.ideal_lo:g} kt sweet spot"
    elif kt <= band.ideal_hi:
        note = f"in the groove — {kt:.0f} kt sits in the {band.ideal_lo:g}–{band.ideal_hi:g} kt band"
    elif kt < band.max:
        note = f"pressed — {kt:.0f} kt is past the {band.ideal_hi:g} kt comfort limit"
    else:
        note = f"overpowered — {kt:.0f} kt exceeds the {band.max:g} kt maximum"
    return Factor("wind", score, profile.weight("wind"), note)


def _gust_factor(hour: Hour, profile: BoatProfile) -> Factor | None:
    ratio = hour.gust_ratio
    if ratio is None:
        return None
    raw = ramp(ratio, profile.gust_ratio_max, profile.gust_ratio_ok)
    score = rescale(raw, 0.3)
    spread = (hour.gust_kt or hour.wind_kt) - hour.wind_kt
    if ratio <= profile.gust_ratio_ok:
        note = f"steady — gusting {spread:.0f} kt over ({ratio:.2f}x)"
    elif ratio <= profile.gust_ratio_max:
        note = f"puffy — gusting {spread:.0f} kt over ({ratio:.2f}x, past {profile.gust_ratio_ok:.2f}x)"
    else:
        note = f"squirrelly — gusting {spread:.0f} kt over ({ratio:.2f}x)"
    return Factor("gust", score, profile.weight("gust"), note)


def _sea_factor(hour: Hour, profile: BoatProfile) -> Factor | None:
    if hour.wave_ft is None:
        return None
    raw = ramp(hour.wave_ft, profile.wave_max_ft, profile.wave_ok_ft)
    score = rescale(raw, 0.1)
    if hour.wave_ft <= profile.wave_ok_ft:
        note = f"manageable — {hour.wave_ft:.1f} ft, at or under {profile.wave_ok_ft:g} ft"
    elif hour.wave_ft < profile.wave_max_ft:
        note = f"lumpy — {hour.wave_ft:.1f} ft, past the {profile.wave_ok_ft:g} ft comfort mark"
    else:
        note = f"heavy — {hour.wave_ft:.1f} ft, at or over the {profile.wave_max_ft:g} ft limit"
    return Factor("sea", score, profile.weight("sea"), note)


def _precip_factor(hour: Hour, profile: BoatProfile) -> Factor | None:
    if hour.precip_pct is None:
        return None
    score = rescale(1.0 - clamp(hour.precip_pct / 100.0, 0.0, 1.0), 0.3)
    if hour.precip_pct < 15:
        note = f"dry — {hour.precip_pct:.0f}% chance of precipitation"
    elif hour.precip_pct < 50:
        note = f"showery — {hour.precip_pct:.0f}% chance of precipitation"
    else:
        note = f"wet — {hour.precip_pct:.0f}% chance of precipitation"
    return Factor("precip", score, profile.weight("precip"), note)


def _comfort_factor(hour: Hour, profile: BoatProfile) -> Factor | None:
    temp = hour.feels_like_f if hour.feels_like_f is not None else hour.temp_f
    if temp is None:
        return None
    lo, hi = profile.comfort_f
    raw = plateau(temp, profile.comfort_min_f, lo, hi, profile.comfort_max_f)
    score = rescale(raw, 0.25)
    if temp < lo:
        note = f"chilly — feels like {temp:.0f}°F, under {lo:g}°F"
    elif temp <= hi:
        note = f"pleasant — feels like {temp:.0f}°F"
    else:
        note = f"baking — feels like {temp:.0f}°F, over {hi:g}°F"
    return Factor("comfort", score, profile.weight("comfort"), note)


def _sky_factor(hour: Hour, profile: BoatProfile) -> Factor | None:
    if hour.sky_pct is None:
        return None
    score = rescale(1.0 - clamp(hour.sky_pct / 100.0, 0.0, 1.0), 0.6)
    return Factor("sky", score, profile.weight("sky"), f"{hour.sky_phrase} — {hour.sky_pct:.0f}% cloud")


def _hazard_vetoes(hazards: Iterable[Hazard], hour: Hour) -> list[Veto]:
    vetoes: list[Veto] = []
    for hazard in hazards:
        if not hazard.covers(hour.time):
            continue
        event = hazard.event.strip().lower()
        if event in CRITICAL_EVENTS:
            vetoes.append(Veto(f"{hazard.event} in force", CRITICAL_CAP, hard=True))
        elif event in CAUTION_EVENTS:
            vetoes.append(Veto(f"{hazard.event} in force", CAUTION_CAP, hard=False))
    return vetoes


def score_hour(
    hour: Hour,
    profile: BoatProfile,
    hazards: Sequence[Hazard] = (),
) -> Score:
    """Score a single forecast hour for a given boat.

    Args:
        hour: Normalized conditions for one hour.
        profile: The boat and skipper the score is computed for.
        hazards: Active NWS products; only those covering ``hour.time`` apply.

    Returns:
        A :class:`~sailing_conditions.models.Score` carrying the value, the
        verdict, every contributing factor and every veto that fired.
    """
    factors = [
        f
        for f in (
            _wind_factor(hour, profile),
            _gust_factor(hour, profile),
            _sea_factor(hour, profile),
            _precip_factor(hour, profile),
            _comfort_factor(hour, profile),
            _sky_factor(hour, profile),
        )
        if f is not None
    ]

    total_weight = sum(f.weight for f in factors)
    if total_weight <= 0:
        return Score(0.0, Verdict.NO_GO, tuple(factors), (Veto("no usable forecast data", 0.0),))

    log_sum = sum(f.weight * math.log(max(f.score, FACTOR_FLOOR)) for f in factors)
    value = 10.0 * math.exp(log_sum / total_weight)

    vetoes: list[Veto] = []
    if hour.thunder_pct is not None and hour.thunder_pct >= profile.thunder_veto_pct:
        vetoes.append(Veto(f"lightning risk — {hour.thunder_pct:.0f}% chance of thunder", 1.0))
    if hour.wind_kt >= profile.wind.max:
        vetoes.append(Veto(f"wind {hour.wind_kt:.0f} kt at or past the {profile.wind.max:g} kt maximum", 2.5))
    if hour.gust_kt is not None and hour.gust_kt >= profile.wind.max * 1.2:
        vetoes.append(Veto(f"gusts to {hour.gust_kt:.0f} kt", 3.0, hard=False))
    if hour.wave_ft is not None and hour.wave_ft >= profile.wave_max_ft:
        # A comfort limit, not a hazard: the skipper gets to make this call.
        vetoes.append(
            Veto(f"seas {hour.wave_ft:.1f} ft at or past the {profile.wave_max_ft:g} ft limit", 3.0, hard=False)
        )
    vetoes.extend(_hazard_vetoes(hazards, hour))

    for veto in vetoes:
        value = min(value, veto.cap)

    value = round(clamp(value, 0.0, 10.0), 1)
    verdict = Verdict.from_score(value, vetoed=any(v.hard for v in vetoes))
    return Score(value, verdict, tuple(factors), tuple(vetoes))


def score_hours(
    hours: Iterable[Hour],
    profile: BoatProfile,
    hazards: Sequence[Hazard] = (),
) -> list[Score]:
    """Score a sequence of hours against one profile."""
    return [score_hour(hour, profile, hazards) for hour in hours]
