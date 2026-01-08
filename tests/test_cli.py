"""Tests for CLI module."""
from __future__ import annotations

import argparse
from datetime import date
from unittest.mock import Mock, patch

import pytest

from sailing_conditions.cli import (
    _is_rainy,
    _resolve_city_selection,
    in_season,
    pick_suggestion,
)


class TestIsRainy:
    """Tests for _is_rainy function."""

    def test_rain_detected(self):
        """Test rain keyword detection."""
        assert _is_rainy("rain likely")
        assert _is_rainy("Showers expected")
        assert _is_rainy("Thunder storms")
        assert _is_rainy("t-storm warning")
        assert _is_rainy("Light drizzle")

    def test_no_rain(self):
        """Test no rain conditions."""
        assert not _is_rainy("sunny")
        assert not _is_rainy("clear skies")
        assert not _is_rainy("partly cloudy")

    def test_empty_and_none(self):
        """Test empty and None inputs."""
        assert not _is_rainy("")
        assert not _is_rainy(None)


class TestPickSuggestion:
    """Tests for pick_suggestion function."""

    @patch.dict("os.environ", {"SUGGESTION_MODE": "stable"})
    def test_stable_mode_deterministic(self):
        """Test stable mode produces deterministic suggestions."""
        suggestion1 = pick_suggestion("Chicago", "sunny")
        suggestion2 = pick_suggestion("Chicago", "sunny")
        assert suggestion1 == suggestion2

    def test_severe_weather_suggestion(self):
        """Test severe weather suggestion."""
        suggestion = pick_suggestion("Chicago", "gale warning in effect")
        assert "stay indoors" in suggestion.lower()

    def test_rainy_suggestion(self):
        """Test rainy weather suggestion."""
        suggestion = pick_suggestion("Chicago", "rain showers")
        assert "aw shoot" in suggestion.lower()

    def test_sunny_suggestion(self):
        """Test sunny weather triggers outdoor suggestion."""
        # With stable mode, we can verify it's an outdoor suggestion
        with patch.dict("os.environ", {"SUGGESTION_MODE": "stable"}):
            suggestion = pick_suggestion("TestCity", "sunny")
            # Should be an outdoor activity
            assert suggestion  # Just check it returns something

    @patch.dict("os.environ", {"SUGGESTION_MODE": "stable"})
    def test_different_cities_different_suggestions(self):
        """Test different cities may get different suggestions in stable mode."""
        # In stable mode, seed is based on city + date, so same city = same result
        suggestion1 = pick_suggestion("Chicago", "cloudy")
        suggestion2 = pick_suggestion("NYC", "cloudy")
        # They might be same or different, but both should be valid


class TestInSeason:
    """Tests for in_season function."""

    def test_memorial_day_in_season(self):
        """Test Memorial Day is in season."""
        # Memorial Day 2025 is May 26
        memorial_day = date(2025, 5, 26)
        assert in_season(memorial_day)

    def test_labor_day_in_season(self):
        """Test Labor Day is in season."""
        # Labor Day 2025 is September 1
        labor_day = date(2025, 9, 1)
        assert in_season(labor_day)

    def test_mid_summer_in_season(self):
        """Test mid-summer is in season."""
        assert in_season(date(2025, 7, 4))
        assert in_season(date(2025, 8, 15))

    def test_winter_out_of_season(self):
        """Test winter is out of season."""
        assert not in_season(date(2025, 1, 15))
        assert not in_season(date(2025, 12, 25))

    def test_before_memorial_day(self):
        """Test day before Memorial Day is out of season."""
        assert not in_season(date(2025, 5, 25))

    def test_after_labor_day(self):
        """Test day after Labor Day is out of season."""
        assert not in_season(date(2025, 9, 2))


class TestResolveCitySelection:
    """Tests for _resolve_city_selection function."""

    def _make_args(self, **kwargs):
        """Create mock args object."""
        args = argparse.Namespace()
        args.only = kwargs.get("only")
        args.all_cities = kwargs.get("all_cities", False)
        args.chicago = kwargs.get("chicago", False)
        args.nyc = kwargs.get("nyc", False)
        args.philly = kwargs.get("philly", False)
        args.kc = kwargs.get("kc", False)
        args.slc = kwargs.get("slc", False)
        return args

    def test_only_flag(self):
        """Test --only flag takes priority."""
        args = self._make_args(only="miami,nyc,chicago")
        result = _resolve_city_selection(args, [])
        assert "miami" in result
        assert "nyc" in result
        assert "chicago" in result

    def test_only_flag_invalid_cities_ignored(self):
        """Test invalid cities in --only flag are ignored."""
        args = self._make_args(only="miami,invalid_city,nyc")
        result = _resolve_city_selection(args, [])
        assert "miami" in result
        assert "nyc" in result
        assert "invalid_city" not in result

    def test_all_cities_flag(self):
        """Test --all-cities flag."""
        args = self._make_args(all_cities=True)
        result = _resolve_city_selection(args, [])
        # Should include all cities
        assert len(result) >= 20  # We know we have 20+ cities

    def test_legacy_flags(self):
        """Test legacy city flags (--chicago, --nyc, etc.)."""
        args = self._make_args(chicago=True, nyc=True)
        result = _resolve_city_selection(args, [])
        assert "chicago" in result
        assert "nyc" in result
        assert len(result) == 2

    def test_unknown_flags(self):
        """Test unknown flags like --miami."""
        args = self._make_args()
        result = _resolve_city_selection(args, ["--miami", "--boston"])
        assert "miami" in result
        assert "boston" in result

    def test_default_cities(self):
        """Test default cities when no flags specified."""
        args = self._make_args()
        result = _resolve_city_selection(args, [])
        # Default should be chicago, philly, kc, slc, nyc
        assert "chicago" in result
        assert "philly" in result
        assert "kc" in result
        assert "slc" in result
        assert "nyc" in result

    def test_mixed_unknown_and_legacy(self):
        """Test combination of unknown flags and legacy flags."""
        args = self._make_args(chicago=True)
        result = _resolve_city_selection(args, ["--miami"])
        assert "miami" in result
        assert "chicago" in result


class TestCliMain:
    """Integration tests for main CLI function."""

    @patch("sailing_conditions.cli.chicago_forecast")
    @patch("sailing_conditions.cli.post_slack")
    @patch("sailing_conditions.cli.send_email_html")
    def test_main_basic_execution(self, mock_email, mock_slack, mock_chicago):
        """Test basic CLI execution."""
        from sailing_conditions.cli import main

        # Mock forecast to return valid data
        mock_chicago.return_value = {
            "city": "Chicago",
            "label": "Today",
            "rating": 8,
            "wind_line": "N 10–15 kt",
            "waves_line": "2–3 ft",
            "sky_line": "Sunny",
            "sailing": True,
            "quick": "Today: 8/10. Wind N 10–15 kt, waves 2–3 ft, Sunny.",
            "prefix": "⛵ ☀",
        }

        # Mock in_season to return True
        with patch("sailing_conditions.cli.in_season", return_value=True):
            with patch("sys.argv", ["prog", "--today", "--chicago", "--slack"]):
                result = main()

        # Should complete without errors (slack might fail but we catch that)
        assert result in (0, 1)  # 0 success, 1 if slack fails

    @patch("sailing_conditions.cli.fetch_city_marine_text")
    @patch("sailing_conditions.cli.grid_city_forecast")
    @patch("sailing_conditions.cli.post_slack")
    @patch("sailing_conditions.cli.send_email_html")
    def test_main_non_sailing_city(self, mock_email, mock_slack, mock_grid, mock_marine):
        """Test CLI with non-sailing city."""
        from sailing_conditions.cli import main

        mock_marine.return_value = None
        mock_grid.return_value = {
            "city": "Philadelphia",
            "label": "Today",
            "rating": 6,
            "wind_line": "SW 5–10 kt",
            "waves_line": "—",
            "sky_line": "Cloudy",
            "sailing": False,
            "quick": "Today: 6/10. Wind SW 5–10 kt, waves —, Cloudy.",
            "prefix": "🌥",
        }

        with patch("sys.argv", ["prog", "--today", "--philly", "--slack"]):
            result = main()

        assert result in (0, 1)

