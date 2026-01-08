"""Tests for forecast module."""
from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from sailing_conditions.forecast import (
    _deg_to_compass,
    _format_waves,
    _format_wind,
    _pack,
    _pick_present_day_label,
    _wind_from_grid,
)


class TestWindFromGrid:
    """Tests for _wind_from_grid function."""

    def test_range_format(self):
        """Test '10 to 15 mph' format."""
        p = {"windSpeed": "10 to 15 mph"}
        result = _wind_from_grid(p)
        assert result is not None
        # 10 mph ≈ 8.7 kt, 15 mph ≈ 13 kt
        assert result[0] < result[1]

    def test_single_speed(self):
        """Test '15 mph' format."""
        p = {"windSpeed": "15 mph"}
        result = _wind_from_grid(p)
        assert result is not None
        assert result[0] <= result[1]

    def test_around_format(self):
        """Test 'around 10 mph' format."""
        p = {"windSpeed": "around 10 mph"}
        result = _wind_from_grid(p)
        assert result is not None

    def test_directional_format(self):
        """Test 'north wind 5 to 10 mph' format."""
        p = {"windSpeed": "north wind 5 to 10 mph"}
        result = _wind_from_grid(p)
        assert result is not None
        assert result[0] < result[1]

    def test_light_and_variable(self):
        """Test 'light and variable' format."""
        p = {"windSpeed": "light and variable"}
        result = _wind_from_grid(p)
        assert result == (0, 5)

    def test_calm(self):
        """Test 'calm' format."""
        p = {"windSpeed": "calm"}
        result = _wind_from_grid(p)
        assert result == (0, 5)

    def test_empty_wind_speed(self):
        """Test empty wind speed."""
        p = {"windSpeed": ""}
        result = _wind_from_grid(p)
        assert result is None

    def test_missing_wind_speed(self):
        """Test missing wind speed."""
        p = {}
        result = _wind_from_grid(p)
        assert result is None


class TestDegToCompass:
    """Tests for _deg_to_compass function."""

    def test_north(self):
        """Test north direction."""
        assert _deg_to_compass(0) == "N"
        assert _deg_to_compass(360) == "N"

    def test_east(self):
        """Test east direction."""
        assert _deg_to_compass(90) == "E"

    def test_south(self):
        """Test south direction."""
        assert _deg_to_compass(180) == "S"

    def test_west(self):
        """Test west direction."""
        assert _deg_to_compass(270) == "W"

    def test_intermediate_directions(self):
        """Test intermediate directions."""
        assert _deg_to_compass(45) == "NE"
        assert _deg_to_compass(135) == "SE"
        assert _deg_to_compass(225) == "SW"
        assert _deg_to_compass(315) == "NW"

    def test_none_input(self):
        """Test None input."""
        assert _deg_to_compass(None) is None


class TestFormatWind:
    """Tests for _format_wind function."""

    def test_direction_and_range(self):
        """Test with direction and range."""
        result = _format_wind("N", (10, 15))
        assert result == "N 10–15 kt"

    def test_range_only(self):
        """Test with range only."""
        result = _format_wind(None, (10, 15))
        assert result == "10–15 kt"

    def test_direction_only(self):
        """Test with direction only."""
        result = _format_wind("N", None)
        assert result == "N"

    def test_no_data(self):
        """Test with no data."""
        result = _format_wind(None, None)
        assert result == "—"


class TestFormatWaves:
    """Tests for _format_waves function."""

    def test_range(self):
        """Test wave range formatting."""
        result = _format_waves((2.0, 4.0))
        assert result == "2.0–4.0 ft"

    def test_single_value(self):
        """Test single wave value."""
        result = _format_waves((3.0, 3.0))
        assert result == "3.0 ft"

    def test_close_values(self):
        """Test close values (within 0.1 ft)."""
        result = _format_waves((3.0, 3.05))
        assert result == "3.0 ft"  # Should show single value

    def test_no_waves(self):
        """Test with no wave data."""
        result = _format_waves(None)
        assert result == "—"


class TestPickPresentDayLabel:
    """Tests for _pick_present_day_label function."""

    def test_rest_of_today_found(self):
        """Test when REST OF TODAY is found."""
        text = ".REST OF TODAY... Wind N 10-15 kt.\n.TONIGHT... Calm."
        result = _pick_present_day_label(text)
        assert result == "REST OF TODAY"

    def test_today_fallback(self):
        """Test fallback to TODAY."""
        text = ".TODAY... Sunny.\n.TONIGHT... Clear."
        result = _pick_present_day_label(text)
        assert result == "TODAY"

    def test_this_afternoon_fallback(self):
        """Test fallback to THIS AFTERNOON."""
        text = ".THIS AFTERNOON... Cloudy.\n.TONIGHT... Clear."
        result = _pick_present_day_label(text)
        assert result == "THIS AFTERNOON"

    def test_empty_text(self):
        """Test with empty text."""
        result = _pick_present_day_label("")
        assert result == "TODAY"

    def test_no_matching_heading(self):
        """Test when no standard heading found."""
        text = "Some text without standard headings."
        result = _pick_present_day_label(text)
        assert result == "TODAY"


class TestPack:
    """Tests for _pack function."""

    def test_basic_pack(self):
        """Test basic packing."""
        result = _pack(
            city="Chicago",
            label="TODAY",
            rating=8,
            wind="N 10–15 kt",
            waves="2–3 ft",
            sky="Sunny",
            sailing=True,
            quick="Today: 8/10. Wind N 10–15 kt, waves 2–3 ft, Sunny.",
            prefix="⛵ ☀",
        )

        assert result["city"] == "Chicago"
        assert result["label"] == "Today"  # Should be title-cased
        assert result["rating"] == 8
        assert result["wind_line"] == "N 10–15 kt"
        assert result["waves_line"] == "2–3 ft"
        assert result["sky_line"] == "Sunny"
        assert result["sailing"] is True
        assert result["prefix"] == "⛵ ☀"

    def test_label_title_casing(self):
        """Test that label is title-cased."""
        result = _pack("City", "TOMORROW", 5, "—", "—", "—", False, "quick", "☀")
        assert result["label"] == "Tomorrow"

        result = _pack("City", "saturday", 5, "—", "—", "—", False, "quick", "☀")
        assert result["label"] == "Saturday"


class TestForecastIntegration:
    """Integration tests for forecast functions."""

    @patch("sailing_conditions.forecast.fetch_tgftp_text")
    @patch("sailing_conditions.forecast.fetch_ndbc_latest")
    @patch("sailing_conditions.forecast.fetch_grid_periods")
    def test_chicago_forecast_fallback(self, mock_grid, mock_ndbc, mock_tgftp):
        """Test Chicago forecast falls back to grid when marine data unavailable."""
        from sailing_conditions.forecast import chicago_forecast

        # No marine data
        mock_tgftp.return_value = None
        mock_ndbc.return_value = None

        # Grid data available
        mock_grid.return_value = [
            {
                "name": "Today",
                "startTime": "2025-01-07T12:00:00-06:00",
                "windSpeed": "10 to 15 mph",
                "windDirection": "N",
                "shortForecast": "Sunny",
                "temperature": 35,
            }
        ]

        result = chicago_forecast("TODAY")

        assert result is not None
        assert result["city"] == "Chicago"
        assert result["sailing"] is True

    @patch("sailing_conditions.forecast.fetch_city_marine_text")
    @patch("sailing_conditions.forecast.fetch_grid_periods")
    def test_marine_city_forecast_fallback(self, mock_grid, mock_marine):
        """Test marine city falls back to grid when marine data unavailable."""
        from sailing_conditions.forecast import marine_city_forecast

        # No marine data
        mock_marine.return_value = None

        # Grid data available
        mock_grid.return_value = [
            {
                "name": "Today",
                "startTime": "2025-01-07T12:00:00-05:00",
                "windSpeed": "8 to 12 mph",
                "windDirection": "S",
                "shortForecast": "Partly cloudy",
                "temperature": 72,
            }
        ]

        result = marine_city_forecast("miami", "TODAY")

        assert result is not None
        assert result["city"] == "Miami"
        assert result["sailing"] is True

    @patch("sailing_conditions.forecast.fetch_grid_periods")
    def test_grid_city_forecast(self, mock_grid):
        """Test grid-only city forecast."""
        from sailing_conditions.forecast import grid_city_forecast

        mock_grid.return_value = [
            {
                "name": "Today",
                "startTime": "2025-01-07T12:00:00-06:00",
                "windSpeed": "5 to 10 mph",
                "windDirection": "W",
                "shortForecast": "Sunny",
                "temperature": 45,
            }
        ]

        result = grid_city_forecast("philly", "TODAY")

        assert result is not None
        assert result["city"] == "Philadelphia"
        assert result["sailing"] is False
        assert result["waves_line"] == "—"  # Grid cities have no wave data

