"""Text parsing utilities for weather forecasts."""
from __future__ import annotations

import re
from typing import Optional, Tuple

# Wind & direction patterns
WIND_RE = re.compile(
    r"(\d{1,2})\s*(?:to|-|–|—)\s*(\d{1,2})\s*(?:kt|knots?)|(\d{1,2})\s*(?:kt|knots?)",
    re.IGNORECASE,
)
DIR_RE = re.compile(
    r"\b(NNE|ENE|ESE|SSE|SSW|WSW|WNW|NNW|N|NE|E|SE|S|SW|W|NW)\b",
    re.IGNORECASE,
)

# Waves / seas patterns — accept either word, with ranges or single values, plus "around X ft"
WAVE_RE = re.compile(
    r"(?:(?:waves?|seas?)\s*)?(?:around\s*)?(\d(?:\.\d)?)\s*(?:to|-|–|—)\s*(\d(?:\.\d)?)\s*(?:ft|feet)"
    r"|(?:(?:waves?|seas?)\s*)?(?:around\s*)?(\d(?:\.\d)?)\s*(?:ft|feet)",
    re.IGNORECASE,
)

WAVE_SPECIAL_PATTERNS = [
    # "1 ft or less", "less than 1 ft"
    re.compile(r"(?:1\s*ft\s*or\s*less|less\s*than\s*1\s*ft)", re.IGNORECASE),
    # "waves around X ft" / "seas around X ft"
    re.compile(r"(?:waves?|seas?)\s*around\s*(\d(?:\.\d)?)\s*(?:ft|feet)", re.IGNORECASE),
    # plain "around X ft"
    re.compile(r"\baround\s*(\d(?:\.\d)?)\s*(?:ft|feet)", re.IGNORECASE),
]

# Sky keywords (loose)
SKY_RE = re.compile(
    r"\b(sunny|clear|partly cloudy|mostly sunny|mostly clear|cloudy|showers|storms?|thunder|rain|overcast)\b",
    re.IGNORECASE,
)

# Sea-state word mappings (when numerics absent)
SEA_STATE_MAP: dict[str, tuple[float, float]] = {
    "smooth": (0.1, 0.5),
    "light chop": (0.5, 1.5),
    "slight chop": (0.5, 1.5),
    "choppy": (1.5, 3.0),
    "moderate chop": (1.5, 3.0),
    "rough": (3.0, 5.0),
    "very rough": (4.0, 7.0),
    "heavy chop": (3.0, 5.0),
}
SEA_STATE_KEYS = tuple(sorted(SEA_STATE_MAP.keys(), key=len, reverse=True))


def parse_wind(text: str) -> Tuple[Optional[str], Optional[Tuple[int, int]]]:
    """
    Parse wind direction and speed from text.

    Args:
        text: Text containing wind information

    Returns:
        Tuple of (direction, (low_speed, high_speed)) in knots, or (None, None) if not found
    """
    dm = DIR_RE.search(text or "")
    wdir = dm.group(0).upper() if dm else None
    sp = WIND_RE.search(text or "")
    if sp:
        if sp.group(1) and sp.group(2):
            lo, hi = int(sp.group(1)), int(sp.group(2))
        else:
            lo = hi = int(sp.group(3))
        return wdir, (lo, hi)
    return wdir, None


def parse_waves(text: str) -> Optional[Tuple[float, float]]:
    """
    Parse wave height from text.

    Args:
        text: Text containing wave/sea information

    Returns:
        Tuple of (low_height, high_height) in feet, or None if not found
    """
    if not text:
        return None
    m = WAVE_RE.search(text)
    if m:
        if m.group(1) and m.group(2):
            return (float(m.group(1)), float(m.group(2)))
        v = float(m.group(3))
        return (v, v)
    for pat in WAVE_SPECIAL_PATTERNS:
        mm = pat.search(text)
        if mm and mm.groups():
            v = float(mm.group(1))
            return (max(0.1, v - 0.5), v + 0.5)
        if pat.search(text):
            return (0.5, 1.0)
    lower = (text or "").lower()
    for key in SEA_STATE_KEYS:
        if key in lower:
            return SEA_STATE_MAP[key]
    return None


def parse_sky(text: str) -> Optional[str]:
    """
    Parse sky/weather conditions from text.

    Args:
        text: Text containing sky/weather description

    Returns:
        Sky condition string (lowercase), or None if not found
    """
    m = SKY_RE.search(text or "")
    return m.group(0).lower() if m else None


def compute_rating(
    wind_kts: Optional[Tuple[int, int]],
    waves_ft: Optional[Tuple[float, float]],
    sky: Optional[str],
) -> int:
    """
    Compute a 1-10 sailing condition rating based on wind, waves, and sky conditions.

    The rating algorithm:
    - Starts at 10 (perfect conditions)
    - Subtracts points for high waves (>3ft: -2, >4ft: -4, >5ft: -6)
    - Subtracts points for dangerous wind (>=28kt: -6, >=23kt: -4, >=18kt: -2)
    - Subtracts points for light wind (<5kt: -2, <9kt: -1)
    - Adds/subtracts for sky conditions (sunny: +1, storms: -5, rain: -2)

    Args:
        wind_kts: Wind speed range in knots (low, high)
        waves_ft: Wave height range in feet (low, high)
        sky: Sky/weather description

    Returns:
        Rating from 1 (poor) to 10 (excellent)
    """
    breakdown = compute_rating_breakdown(wind_kts, waves_ft, sky)
    return breakdown["final"]


def compute_rating_breakdown(
    wind_kts: Optional[Tuple[int, int]],
    waves_ft: Optional[Tuple[float, float]],
    sky: Optional[str],
) -> dict:
    """
    Compute a detailed breakdown of the sailing condition rating.

    Args:
        wind_kts: Wind speed range in knots (low, high)
        waves_ft: Wave height range in feet (low, high)
        sky: Sky/weather description

    Returns:
        Dictionary with:
        - base: Starting score (10)
        - wind_adj: Wind adjustment and reason
        - wave_adj: Wave adjustment and reason
        - sky_adj: Sky adjustment and reason
        - raw: Score before clamping
        - final: Final rating (1-10)
    """
    breakdown = {
        "base": 10,
        "wind_adj": 0,
        "wind_reason": None,
        "wave_adj": 0,
        "wave_reason": None,
        "sky_adj": 0,
        "sky_reason": None,
        "raw": 10,
        "final": 5,
    }

    # If we truly have nothing, stay neutral
    if wind_kts is None and waves_ft is None and not sky:
        breakdown["raw"] = 5
        breakdown["final"] = 5
        breakdown["wind_reason"] = "no data"
        breakdown["wave_reason"] = "no data"
        breakdown["sky_reason"] = "no data"
        return breakdown

    score = 10

    # Waves penalty
    if waves_ft:
        hi = max(waves_ft)
        if hi > 5:
            breakdown["wave_adj"] = -6
            breakdown["wave_reason"] = f"dangerous ({hi}ft > 5ft)"
            score -= 6
        elif hi > 4:
            breakdown["wave_adj"] = -4
            breakdown["wave_reason"] = f"very high ({hi}ft > 4ft)"
            score -= 4
        elif hi > 3:
            breakdown["wave_adj"] = -2
            breakdown["wave_reason"] = f"high ({hi}ft > 3ft)"
            score -= 2
        else:
            breakdown["wave_reason"] = f"optimal ({hi}ft ≤ 3ft)"
    else:
        breakdown["wave_reason"] = "no wave data"

    # Wind penalty/bonus
    if wind_kts:
        lo, hi = wind_kts
        wind_adj = 0
        reasons = []

        if hi >= 28:
            wind_adj -= 6
            reasons.append(f"dangerous ({hi}kt ≥ 28kt)")
        elif hi >= 23:
            wind_adj -= 4
            reasons.append(f"very high ({hi}kt ≥ 23kt)")
        elif hi >= 18:
            wind_adj -= 2
            reasons.append(f"high ({hi}kt ≥ 18kt)")
        else:
            reasons.append(f"good max ({hi}kt < 18kt)")

        if lo < 5:
            wind_adj -= 2
            reasons.append(f"too light ({lo}kt < 5kt)")
        elif lo < 9:
            wind_adj -= 1
            reasons.append(f"light ({lo}kt < 9kt)")
        else:
            reasons.append(f"good min ({lo}kt ≥ 9kt)")

        breakdown["wind_adj"] = wind_adj
        breakdown["wind_reason"] = "; ".join(reasons)
        score += wind_adj
    else:
        breakdown["wind_reason"] = "no wind data"

    # Sky bonus/penalty
    if sky:
        s = sky.lower()
        sky_adj = 0
        reasons = []

        if "sunny" in s or "clear" in s:
            sky_adj += 1
            reasons.append("sunny/clear (+1)")
        if "storm" in s or "thunder" in s:
            sky_adj -= 5
            reasons.append("storm/thunder (-5)")
        if "showers" in s or "rain" in s:
            sky_adj -= 2
            reasons.append("showers/rain (-2)")

        if not reasons:
            reasons.append(f"neutral ({sky})")

        breakdown["sky_adj"] = sky_adj
        breakdown["sky_reason"] = "; ".join(reasons)
        score += sky_adj
    else:
        breakdown["sky_reason"] = "no sky data"

    breakdown["raw"] = score
    breakdown["final"] = max(1, min(10, score))
    return breakdown


def normalize_heading(h: str) -> str:
    """
    Normalize a heading string by removing extra whitespace and uppercasing.

    Args:
        h: Heading string to normalize

    Returns:
        Normalized heading string
    """
    return re.sub(r"\s+", " ", (h or "").strip().upper())


def extract_day_blurb(full_text: str, day_heading: str) -> Optional[str]:
    """
    Extract a section of text for a specific day heading from marine forecast text.

    Args:
        full_text: Full marine forecast text
        day_heading: Day heading to extract (e.g., "TODAY", "TOMORROW")

    Returns:
        Extracted text section, or None if not found
    """
    txt = (full_text or "").replace("\r", "")
    dh = normalize_heading(day_heading)
    pattern = rf"(?mis)^\s*\.?{re.escape(dh)}(?:\s+NIGHT)?\.{{3,}}(.*?)(?=^\s*\.?[A-Z][A-Z /-]{{2,}}(?:\s+NIGHT)?\.{{3,}}|\Z)"
    m = re.search(pattern, txt)
    return m.group(0).strip() if m else None


def extract_today_blurb(full_text: str) -> str:
    """
    Extract today's forecast section from marine text, trying multiple heading formats.

    Args:
        full_text: Full marine forecast text

    Returns:
        Today's forecast section, or first paragraph if no specific heading found
    """
    for c in [
        "REST OF TODAY",
        "TODAY",
        "THIS AFTERNOON",
        "LATE THIS AFTERNOON",
        "THIS MORNING",
        "DAYTIME",
    ]:
        sec = extract_day_blurb(full_text, c)
        if sec:
            return sec

    m = re.search(r"(?s)(?:\A|^\s*\n)(.*?)(?:\n\s*\n|\Z)", full_text or "")
    return m.group(1).strip() if m else (full_text or "")
