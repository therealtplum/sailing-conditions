"""JSON serialization.

The schema is written out by hand rather than derived from
:func:`dataclasses.asdict` so that it is a deliberate, stable contract:
renaming an internal field should not silently break someone's script.
``schema_version`` is bumped whenever that contract changes.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from ..models import DayOutlook, Hazard, Hour, Observation, Report, Score, ScoredHour, SunTimes, Window

SCHEMA_VERSION = 2


def _time(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value else None


def hour_to_dict(hour: Hour) -> dict[str, Any]:
    """Serialize one hour of conditions."""
    return {
        "time": _time(hour.time),
        "wind_kt": hour.wind_kt,
        "gust_kt": hour.gust_kt,
        "wind_dir_deg": hour.wind_dir_deg,
        "wind_dir": hour.wind_dir,
        "beaufort": hour.beaufort,
        "wave_ft": hour.wave_ft,
        "temp_f": hour.temp_f,
        "feels_like_f": hour.feels_like_f,
        "precip_pct": hour.precip_pct,
        "thunder_pct": hour.thunder_pct,
        "sky_pct": hour.sky_pct,
        "weather": hour.weather,
    }


def score_to_dict(score: Score) -> dict[str, Any]:
    """Serialize a score with its full explanation."""
    return {
        "value": score.value,
        "verdict": score.verdict.value,
        "vetoed": score.vetoed,
        "factors": [
            {"name": f.name, "score": round(f.score, 4), "weight": f.weight, "note": f.note}
            for f in score.factors
        ],
        "vetoes": [{"reason": v.reason, "cap": v.cap, "hard": v.hard} for v in score.vetoes],
    }


def scored_hour_to_dict(scored: ScoredHour) -> dict[str, Any]:
    """Serialize an hour together with its score."""
    return {**hour_to_dict(scored.hour), "score": score_to_dict(scored.score), "daylight": scored.daylight}


def window_to_dict(window: Window) -> dict[str, Any]:
    """Serialize a sailable window."""
    return {
        "start": _time(window.start),
        "end": _time(window.end),
        "hours": window.length_hours,
        "mean_score": round(window.mean_score, 2),
        "peak_score": window.peak.value,
        "peak_time": _time(window.peak.time),
        "label": window.describe(),
    }


def sun_to_dict(sun: SunTimes) -> dict[str, Any]:
    """Serialize solar events."""
    return {
        "sunrise": _time(sun.sunrise),
        "sunset": _time(sun.sunset),
        "solar_noon": _time(sun.solar_noon),
        "daylight_hours": sun.daylight_hours,
    }


def hazard_to_dict(hazard: Hazard) -> dict[str, Any]:
    """Serialize an active NWS product."""
    return {
        "event": hazard.event,
        "severity": hazard.severity,
        "headline": hazard.headline,
        "onset": _time(hazard.onset),
        "ends": _time(hazard.ends),
    }


def observation_to_dict(observation: Observation) -> dict[str, Any]:
    """Serialize a buoy report."""
    return {
        "station": observation.station,
        "time": _time(observation.time),
        "age_minutes": round(observation.age.total_seconds() / 60, 1),
        "wind_kt": observation.wind_kt,
        "gust_kt": observation.gust_kt,
        "wind_dir_deg": observation.wind_dir_deg,
        "wind_dir": observation.wind_dir,
        "wave_ft": observation.wave_ft,
        "wave_period_s": observation.wave_period_s,
        "air_temp_f": observation.air_temp_f,
        "water_temp_f": observation.water_temp_f,
    }


def day_to_dict(day: DayOutlook, *, hourly: bool = True) -> dict[str, Any]:
    """Serialize one day, optionally including every hour."""
    payload: dict[str, Any] = {
        "date": day.date.isoformat(),
        "score": round(day.score, 2),
        "verdict": day.verdict.value,
        "sun": sun_to_dict(day.sun),
        "windows": [window_to_dict(w) for w in day.windows],
        "best_window": window_to_dict(day.best_window) if day.best_window else None,
    }
    if hourly:
        payload["hours"] = [scored_hour_to_dict(h) for h in day.hours]
    return payload


def report_to_dict(report: Report, *, hourly: bool = True) -> dict[str, Any]:
    """Serialize a full report."""
    return {
        "schema_version": SCHEMA_VERSION,
        "spot": {
            "key": report.spot.key,
            "name": report.spot.name,
            "region": report.spot.region,
            "lat": report.spot.lat,
            "lon": report.spot.lon,
            "buoy": report.spot.buoy,
            "tags": list(report.spot.tags),
        },
        "profile": report.profile_key,
        "generated_at": _time(report.generated_at),
        "timezone": report.timezone,
        "headline": report.headline(),
        "days": [day_to_dict(day, hourly=hourly) for day in report.days],
        "hazards": [hazard_to_dict(h) for h in report.hazards],
        "observation": observation_to_dict(report.observation) if report.observation else None,
        "notes": list(report.notes),
    }


def dumps(reports: list[Report], *, hourly: bool = True, indent: int | None = 2) -> str:
    """Serialize a list of reports to a JSON document."""
    payload = {
        "schema_version": SCHEMA_VERSION,
        "count": len(reports),
        "reports": [report_to_dict(report, hourly=hourly) for report in reports],
    }
    return json.dumps(payload, indent=indent)
