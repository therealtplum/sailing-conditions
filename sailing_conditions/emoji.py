"""Weather emoji selection for sailing conditions."""
from __future__ import annotations

from typing import Optional, Tuple

from .config import SEVERE_WORDS


def is_severe(text: Optional[str]) -> bool:
    """Check if text contains severe weather keywords."""
    return bool(text) and any(k in text.lower() for k in SEVERE_WORDS)


def pick_weather_emoji(
    sailing: bool,
    rating: int,
    sky: Optional[str],
    waves: Optional[Tuple[float, float]],
    wind_rng: Optional[Tuple[int, int]],
    hazards_text: Optional[str],
    temp_f: Optional[int],
    is_non_sailing: bool,
) -> str:
    """
    Select an appropriate weather emoji based on conditions.

    Priority order: severe -> high waves -> rain -> windy (bad) -> cloudy -> sunny -> freezing

    Args:
        sailing: Whether this is a sailing city
        rating: Current sailing rating (1-10)
        sky: Sky condition description
        waves: Wave height range in feet (low, high)
        wind_rng: Wind speed range in knots (low, high)
        hazards_text: Hazard/warning text
        temp_f: Temperature in Fahrenheit
        is_non_sailing: Whether this is explicitly a non-sailing city

    Returns:
        Emoji string representing the weather
    """
    s = (sky or "").lower()

    if is_severe(hazards_text or s):
        return "❌"
    if waves and max(waves) > 4.0 and sailing:
        return "🌊"
    if any(k in s for k in ["rain", "shower", "thunder", "storm", "drizzle", "t-storm"]):
        return "🌧"
    if wind_rng and rating < 7 and (wind_rng[1] >= 20):
        return "💨"
    if any(k in s for k in ["cloud", "overcast"]):
        return "🌥"
    if any(k in s for k in ["sunny", "clear", "mostly sunny", "mostly clear"]):
        return "☀"
    if is_non_sailing and (temp_f is not None) and temp_f < 35:
        return "🥶"
    return "🌥" if "cloud" in s else "☀"


def compose_prefix_emoji(sailing: bool, rating: int, weather_emoji: str) -> str:
    """
    Compose a prefix emoji string for the forecast.

    Args:
        sailing: Whether this is a sailing city
        rating: Current sailing rating (1-10)
        weather_emoji: Weather emoji to include

    Returns:
        Prefix string with appropriate emojis
    """
    return f"⛵ {weather_emoji}" if sailing and rating >= 6 else weather_emoji
