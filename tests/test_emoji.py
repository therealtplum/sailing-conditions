"""Tests for emoji module."""
from __future__ import annotations

import pytest

from sailing_conditions.emoji import compose_prefix_emoji, is_severe, pick_weather_emoji


class TestIsSevere:
    """Tests for is_severe function."""

    def test_hazard_detected(self):
        """Test hazard keyword detection."""
        assert is_severe("hazard warning in effect")

    def test_warning_detected(self):
        """Test warning keyword detection."""
        assert is_severe("Small craft warning")

    def test_gale_detected(self):
        """Test gale keyword detection."""
        assert is_severe("Gale force winds expected")

    def test_storm_detected(self):
        """Test storm keyword detection."""
        assert is_severe("Storm approaching")

    def test_hurricane_detected(self):
        """Test hurricane keyword detection."""
        assert is_severe("Hurricane conditions")

    def test_freezing_spray_detected(self):
        """Test heavy freezing spray detection."""
        assert is_severe("hvy freezing spray expected")

    def test_no_severe_conditions(self):
        """Test with no severe conditions."""
        assert not is_severe("sunny and clear")
        assert not is_severe("partly cloudy")

    def test_empty_string(self):
        """Test with empty string."""
        assert not is_severe("")

    def test_none_input(self):
        """Test with None input."""
        assert not is_severe(None)


class TestPickWeatherEmoji:
    """Tests for pick_weather_emoji function."""

    def test_severe_conditions(self):
        """Test emoji for severe conditions."""
        emoji = pick_weather_emoji(
            sailing=True,
            rating=3,
            sky="clear",
            waves=(2, 3),
            wind_rng=(10, 15),
            hazards_text="gale warning",
            temp_f=70,
            is_non_sailing=False,
        )
        assert emoji == "❌"

    def test_high_waves(self):
        """Test emoji for high waves."""
        emoji = pick_weather_emoji(
            sailing=True,
            rating=5,
            sky="clear",
            waves=(4, 5),
            wind_rng=(10, 15),
            hazards_text=None,
            temp_f=70,
            is_non_sailing=False,
        )
        assert emoji == "🌊"

    def test_rain(self):
        """Test emoji for rain."""
        emoji = pick_weather_emoji(
            sailing=True,
            rating=5,
            sky="rain showers",
            waves=(1, 2),
            wind_rng=(10, 15),
            hazards_text=None,
            temp_f=70,
            is_non_sailing=False,
        )
        assert emoji == "🌧"

    def test_high_wind_bad_rating(self):
        """Test emoji for high wind with bad rating."""
        emoji = pick_weather_emoji(
            sailing=True,
            rating=5,
            sky="clear",
            waves=(1, 2),
            wind_rng=(15, 22),
            hazards_text=None,
            temp_f=70,
            is_non_sailing=False,
        )
        assert emoji == "💨"

    def test_cloudy(self):
        """Test emoji for cloudy conditions."""
        emoji = pick_weather_emoji(
            sailing=True,
            rating=8,
            sky="mostly cloudy",
            waves=(1, 2),
            wind_rng=(10, 15),
            hazards_text=None,
            temp_f=70,
            is_non_sailing=False,
        )
        assert emoji == "🌥"

    def test_sunny(self):
        """Test emoji for sunny conditions."""
        emoji = pick_weather_emoji(
            sailing=True,
            rating=9,
            sky="sunny",
            waves=(1, 2),
            wind_rng=(10, 15),
            hazards_text=None,
            temp_f=70,
            is_non_sailing=False,
        )
        assert emoji == "☀"

    def test_freezing_non_sailing(self):
        """Test emoji for freezing temps in non-sailing city."""
        # Note: freezing check only triggers if no other conditions match first
        # Using a neutral sky that doesn't match sunny, clear, cloudy, etc.
        emoji = pick_weather_emoji(
            sailing=False,
            rating=5,
            sky="fair",  # "fair" doesn't match any other condition keywords
            waves=None,
            wind_rng=(5, 10),
            hazards_text=None,
            temp_f=25,
            is_non_sailing=True,
        )
        assert emoji == "🥶"

    def test_thunderstorm(self):
        """Test emoji for thunderstorm - 'storm' is in SEVERE_WORDS so returns ❌."""
        emoji = pick_weather_emoji(
            sailing=True,
            rating=3,
            sky="thunderstorm",
            waves=(2, 3),
            wind_rng=(15, 25),
            hazards_text=None,
            temp_f=75,
            is_non_sailing=False,
        )
        # "storm" is in SEVERE_WORDS, so severe check triggers first
        assert emoji == "❌"

    def test_rain_showers(self):
        """Test emoji for rain (not storm)."""
        emoji = pick_weather_emoji(
            sailing=True,
            rating=5,
            sky="rain showers",
            waves=(2, 3),
            wind_rng=(10, 15),
            hazards_text=None,
            temp_f=65,
            is_non_sailing=False,
        )
        assert emoji == "🌧"


class TestComposePrefixEmoji:
    """Tests for compose_prefix_emoji function."""

    def test_good_sailing_conditions(self):
        """Test prefix for good sailing conditions."""
        prefix = compose_prefix_emoji(sailing=True, rating=8, weather_emoji="☀")
        assert prefix == "⛵ ☀"

    def test_poor_sailing_conditions(self):
        """Test prefix for poor sailing conditions."""
        prefix = compose_prefix_emoji(sailing=True, rating=4, weather_emoji="🌧")
        assert prefix == "🌧"

    def test_non_sailing_city(self):
        """Test prefix for non-sailing city."""
        prefix = compose_prefix_emoji(sailing=False, rating=8, weather_emoji="☀")
        assert prefix == "☀"

    def test_threshold_rating(self):
        """Test prefix at rating threshold (6)."""
        prefix = compose_prefix_emoji(sailing=True, rating=6, weather_emoji="🌥")
        assert prefix == "⛵ 🌥"

        prefix = compose_prefix_emoji(sailing=True, rating=5, weather_emoji="🌥")
        assert prefix == "🌥"

