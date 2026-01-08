"""Forecast generation for different city types."""
from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

from .cities import CITIES
from .config import CHICAGO_NEARSHORE, MPH_TO_KNOTS, NDBC_STATION
from .emoji import compose_prefix_emoji, pick_weather_emoji
from .fetchers import (
    fetch_city_marine_text,
    fetch_grid_periods,
    fetch_ndbc_latest,
    fetch_tgftp_text,
    grid_pick_day,
)
from .parsers import (
    compute_rating,
    extract_day_blurb,
    extract_today_blurb,
    parse_sky,
    parse_waves,
    parse_wind,
)


def _wind_from_grid(p: dict) -> Optional[Tuple[int, int]]:
    """
    Robustly parse NWS grid 'windSpeed' strings.

    Handles formats like:
      - "10 to 15 mph"
      - "15 mph"
      - "around 5 mph"
      - "north wind 5 to 10 mph"
      - "light and variable" / "calm"

    Args:
        p: NWS grid period dictionary

    Returns:
        Tuple of (low_speed, high_speed) in knots, or None if parsing fails
    """
    wind_text = (p.get("windSpeed") or "").strip().lower()

    m_rng = re.search(r"(\d{1,2})\D+(\d{1,2})\s*mph", wind_text)
    if m_rng:
        lo, hi = int(m_rng.group(1)), int(m_rng.group(2))
        return (round(lo * MPH_TO_KNOTS), round(hi * MPH_TO_KNOTS))

    m_one = re.search(r"(\d{1,2})\s*mph", wind_text)
    if m_one:
        v = int(m_one.group(1))
        v_kt = round(v * MPH_TO_KNOTS)
        return (max(0, v_kt - 1), v_kt + 1)

    m_around = re.search(r"around\s+(\d{1,2})\s*mph", wind_text)
    if m_around:
        v = int(m_around.group(1))
        v_kt = round(v * MPH_TO_KNOTS)
        return (max(0, v_kt - 1), v_kt + 1)

    m_dir_rng = re.search(
        r"(north|northeast|east|southeast|south|southwest|west|northwest)\s+wind\s+(\d{1,2})\D+(\d{1,2})\s*mph",
        wind_text,
    )
    if m_dir_rng:
        lo, hi = int(m_dir_rng.group(2)), int(m_dir_rng.group(3))
        return (round(lo * MPH_TO_KNOTS), round(hi * MPH_TO_KNOTS))

    if "light" in wind_text or "variable" in wind_text or "calm" in wind_text:
        return (0, 5)

    return None


def chicago_forecast(label: str) -> Dict:
    """
    Generate forecast for Chicago with special handling for marine zones and NDBC observations.

    Args:
        label: Day label (e.g., "TODAY", "TOMORROW")

    Returns:
        Dictionary with forecast data including rating, wind, waves, sky, etc.
    """
    # Build marine text from LMZ files
    full = []
    for rel in CHICAGO_NEARSHORE:
        t = fetch_tgftp_text(rel)
        if t:
            full.append(t)
    marine_text = "\n\n".join(full)

    # Try exact-day extraction; if missing, fall back to the first "today-ish" block
    sec = extract_day_blurb(marine_text, label) if marine_text else None
    if not sec and marine_text:
        sec = extract_today_blurb(marine_text)

    wdir: Optional[str] = None
    wrng: Optional[Tuple[int, int]] = None
    waves: Optional[Tuple[float, float]] = None
    sky: Optional[str] = None
    hazards = sec or None

    if sec:
        wdir, wrng = parse_wind(sec)
        waves = parse_waves(sec)
        sky = parse_sky(sec)
    else:
        periods = fetch_grid_periods(CITIES["chicago"]["lat"], CITIES["chicago"]["lon"])
        if periods:
            p = grid_pick_day(periods, label.title())
            if p:
                wrng = _wind_from_grid(p)
                wdir = p.get("windDirection")
                sky = (p.get("shortForecast") or p.get("detailedForecast") or "").lower()
                waves = None
                hazards = sky

    # Blend CHII2 obs
    obs = fetch_ndbc_latest(NDBC_STATION)
    if obs and obs.get("wspd_kt") is not None:
        comp = _deg_to_compass(obs.get("wdir_deg"))
        if wrng:
            lo, hi = wrng
            mid = int(round(obs["wspd_kt"]))
            if abs(((lo + hi) // 2) - mid) >= 4:
                wrng = (min(lo, mid), max(hi, mid))
        else:
            mid = int(round(obs["wspd_kt"]))
            wrng = (max(0, mid - 1), mid + 1)
        if not wdir and comp:
            wdir = comp

    rating = compute_rating(wrng, waves, sky)
    wind_line = _format_wind(wdir, wrng)
    waves_line = _format_waves(waves)
    sky_line = sky.title() if sky else "—"
    weather_emoji = pick_weather_emoji(True, rating, sky, waves, wrng, hazards, None, False)
    prefix = compose_prefix_emoji(True, rating, weather_emoji)
    quick = f"{label.title()}: {rating}/10. Wind {wind_line}, waves {waves_line}, {sky_line}."
    return _pack("Chicago", label, rating, wind_line, waves_line, sky_line, True, quick, prefix)


def marine_city_forecast(city_key: str, label: str) -> Dict:
    """
    Generate forecast for a marine city (has marine zone forecasts).

    Args:
        city_key: City key from CITIES dictionary
        label: Day label (e.g., "TODAY", "TOMORROW")

    Returns:
        Dictionary with forecast data including rating, wind, waves, sky, etc.
    """
    meta = CITIES[city_key]
    marine_text = fetch_city_marine_text(meta.get("marine_zones") or [])
    wdir: Optional[str] = None
    wrng: Optional[Tuple[int, int]] = None
    waves: Optional[Tuple[float, float]] = None
    sky: Optional[str] = None
    hazards = marine_text or None

    if marine_text:
        sec = extract_day_blurb(marine_text, label)
        if not sec:
            # cover more headings commonly used in ANZ/AMZ/PZZ products
            if label.upper() in (
                "REST OF TODAY",
                "TODAY",
                "THIS AFTERNOON",
                "LATE THIS AFTERNOON",
                "THIS MORNING",
                "DAYTIME",
            ):
                sec = extract_today_blurb(marine_text)
        if sec:
            wdir, wrng = parse_wind(sec)
            waves = parse_waves(sec)
            sky = parse_sky(sec)
            hazards = sec

    temp_f: Optional[int] = None
    if wrng is None and waves is None and sky is None:
        periods = fetch_grid_periods(meta["lat"], meta["lon"])
        if periods:
            p = grid_pick_day(periods, label.title())
            if p:
                wrng = _wind_from_grid(p)
                wdir = p.get("windDirection")
                sky = (p.get("shortForecast") or p.get("detailedForecast") or "").lower()
                temp_f = p.get("temperature")
                waves = None
                hazards = sky

    rating = compute_rating(wrng, waves, sky)
    wind_line = _format_wind(wdir, wrng)
    waves_line = _format_waves(waves)
    sky_line = sky.title() if sky else "—"
    weather_emoji = pick_weather_emoji(True, rating, sky, waves, wrng, hazards, temp_f, False)
    prefix = compose_prefix_emoji(True, rating, weather_emoji)
    quick = f"{label.title()}: {rating}/10. Wind {wind_line}, waves {waves_line}, {sky_line}."
    return _pack(meta["label"], label, rating, wind_line, waves_line, sky_line, True, quick, prefix)


def grid_city_forecast(city_key: str, label: str) -> Dict:
    """
    Generate forecast for a grid-only city (no marine forecasts, uses NWS grid API).

    Args:
        city_key: City key from CITIES dictionary
        label: Day label (e.g., "TODAY", "TOMORROW")

    Returns:
        Dictionary with forecast data including rating, wind, waves (always "—"), sky, etc.
    """
    meta = CITIES[city_key]
    periods = fetch_grid_periods(meta["lat"], meta["lon"])
    wdir: Optional[str] = None
    wrng: Optional[Tuple[int, int]] = None
    waves: Optional[Tuple[float, float]] = None
    sky: Optional[str] = None
    temp_f: Optional[int] = None

    if periods:
        p = grid_pick_day(periods, label.title())
        if p:
            wrng = _wind_from_grid(p)
            wdir = p.get("windDirection")
            sky = (p.get("shortForecast") or p.get("detailedForecast") or "").lower()
            temp_f = p.get("temperature")

    rating = compute_rating(wrng, waves, sky)
    wind_line = _format_wind(wdir, wrng)
    waves_line = "—"
    sky_line = sky.title() if sky else "—"
    weather_emoji = pick_weather_emoji(
        meta["sailing"],
        rating,
        sky,
        None,
        wrng,
        sky,
        temp_f,
        not meta["sailing"],
    )
    prefix = compose_prefix_emoji(meta["sailing"], rating, weather_emoji)
    quick = f"{label.title()}: {rating}/10. Wind {wind_line}, waves {waves_line}, {sky_line}."
    return _pack(meta["label"], label, rating, wind_line, waves_line, sky_line, meta["sailing"], quick, prefix)


def _pick_present_day_label(marine_text: str) -> str:
    """
    Pick the best daytime label that actually exists in the marine text.

    Priority: REST OF TODAY > TODAY > THIS AFTERNOON > LATE THIS AFTERNOON > THIS MORNING > DAYTIME

    Args:
        marine_text: Marine forecast text to search

    Returns:
        Best matching day label
    """
    if not marine_text:
        return "TODAY"
    candidates = [
        "REST OF TODAY",
        "TODAY",
        "THIS AFTERNOON",
        "LATE THIS AFTERNOON",
        "THIS MORNING",
        "DAYTIME",
    ]
    for cand in candidates:
        if extract_day_blurb(marine_text, cand):
            return cand
    return "TODAY"


def _deg_to_compass(deg: Optional[int]) -> Optional[str]:
    """
    Convert wind direction in degrees to compass direction.

    Args:
        deg: Wind direction in degrees (0-360)

    Returns:
        Compass direction (N, NE, E, etc.), or None if deg is None
    """
    if deg is None:
        return None
    dirs = [
        "N",
        "NNE",
        "NE",
        "ENE",
        "E",
        "ESE",
        "SE",
        "SSE",
        "S",
        "SSW",
        "SW",
        "WSW",
        "W",
        "WNW",
        "NW",
        "NNW",
    ]
    i = int((deg / 22.5) + 0.5) % 16
    return dirs[i]


def _format_wind(wdir: Optional[str], wrng: Optional[Tuple[int, int]]) -> str:
    """
    Format wind information as a string.

    Args:
        wdir: Wind direction (compass)
        wrng: Wind speed range in knots (low, high)

    Returns:
        Formatted wind string (e.g., "N 10–15 kt" or "10–15 kt" or "—")
    """
    if wrng and wdir:
        return f"{wdir} {wrng[0]}–{wrng[1]} kt"
    if wrng:
        return f"{wrng[0]}–{wrng[1]} kt"
    if wdir:
        return wdir
    return "—"


def _format_waves(waves: Optional[Tuple[float, float]]) -> str:
    """
    Format wave height information as a string.

    Args:
        waves: Wave height range in feet (low, high)

    Returns:
        Formatted wave string (e.g., "2–4 ft" or "3 ft" or "—")
    """
    if not waves:
        return "—"
    lo, hi = waves
    return f"{lo}–{hi} ft" if abs(hi - lo) > 0.1 else f"{lo} ft"


def _pack(
    city: str,
    label: str,
    rating: int,
    wind: str,
    waves: str,
    sky: str,
    sailing: bool,
    quick: str,
    prefix: str,
) -> Dict:
    """
    Pack forecast data into a standardized dictionary.

    Args:
        city: City name
        label: Day label
        rating: Sailing rating (1-10)
        wind: Formatted wind string
        waves: Formatted waves string
        sky: Sky condition string
        sailing: Whether this is a sailing city
        quick: Quick summary string
        prefix: Emoji prefix string

    Returns:
        Dictionary with all forecast data
    """
    return {
        "city": city,
        "label": label.title(),
        "rating": rating,
        "wind_line": wind,
        "waves_line": waves,
        "sky_line": sky,
        "sailing": sailing,
        "quick": quick,
        "prefix": prefix,
    }
