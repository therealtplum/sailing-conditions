"""Tests for new features: JSON output, week forecast, temperature, verbose mode, etc."""
from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest


class TestComputeRatingBreakdown:
    """Tests for compute_rating_breakdown function."""

    def test_basic_breakdown(self):
        """Test basic rating breakdown."""
        from sailing_conditions.parsers import compute_rating_breakdown

        result = compute_rating_breakdown((12, 15), (2.0, 3.0), "sunny")

        assert result["base"] == 10
        assert result["final"] >= 1
        assert result["final"] <= 10
        assert result["wind_reason"] is not None
        assert result["wave_reason"] is not None
        assert result["sky_reason"] is not None

    def test_breakdown_no_data(self):
        """Test breakdown with no data."""
        from sailing_conditions.parsers import compute_rating_breakdown

        result = compute_rating_breakdown(None, None, None)

        assert result["final"] == 5
        assert result["wind_reason"] == "no data"
        assert result["wave_reason"] == "no data"
        assert result["sky_reason"] == "no data"

    def test_breakdown_high_waves_penalty(self):
        """Test that high waves cause a penalty."""
        from sailing_conditions.parsers import compute_rating_breakdown

        result = compute_rating_breakdown((10, 12), (5.0, 6.0), "clear")

        assert result["wave_adj"] < 0
        assert "dangerous" in result["wave_reason"].lower()

    def test_breakdown_storm_penalty(self):
        """Test that storms cause a penalty."""
        from sailing_conditions.parsers import compute_rating_breakdown

        result = compute_rating_breakdown((10, 12), (2.0, 3.0), "thunderstorms")

        assert result["sky_adj"] < 0
        assert "storm" in result["sky_reason"].lower() or "thunder" in result["sky_reason"].lower()

    def test_breakdown_sunny_bonus(self):
        """Test that sunny skies give a bonus."""
        from sailing_conditions.parsers import compute_rating_breakdown

        result = compute_rating_breakdown((10, 12), (2.0, 3.0), "sunny")

        assert result["sky_adj"] > 0
        assert "sunny" in result["sky_reason"].lower() or "clear" in result["sky_reason"].lower()


class TestJSONOutput:
    """Tests for JSON output formatting."""

    def test_json_output_structure(self):
        """Test JSON output has correct structure."""
        from sailing_conditions.formatters import format_json_output

        entries = [
            {
                "city": "Chicago",
                "city_key": "chicago",
                "label": "Today",
                "rating": 8,
                "wind_line": "N 10–15 kt",
                "waves_line": "2–3 ft",
                "sky_line": "Sunny",
                "sailing": True,
            }
        ]

        result = format_json_output(entries)
        parsed = json.loads(result)

        assert "forecasts" in parsed
        assert "count" in parsed
        assert parsed["count"] == 1
        assert len(parsed["forecasts"]) == 1

    def test_json_output_includes_temperature(self):
        """Test JSON output includes temperature when available."""
        from sailing_conditions.formatters import format_json_output

        entries = [
            {
                "city": "Chicago",
                "city_key": "chicago",
                "label": "Today",
                "rating": 8,
                "wind_line": "N 10–15 kt",
                "waves_line": "2–3 ft",
                "sky_line": "Sunny",
                "sailing": True,
                "temp_f": 75,
                "temp_c": 24,
            }
        ]

        result = format_json_output(entries)
        parsed = json.loads(result)

        forecast = parsed["forecasts"][0]
        assert "temperature" in forecast
        assert forecast["temperature"]["fahrenheit"] == 75
        assert forecast["temperature"]["celsius"] == 24

    def test_json_output_includes_sun_times(self):
        """Test JSON output includes sun times when available."""
        from sailing_conditions.formatters import format_json_output

        entries = [
            {
                "city": "Chicago",
                "city_key": "chicago",
                "label": "Today",
                "rating": 8,
                "wind_line": "—",
                "waves_line": "—",
                "sky_line": "—",
                "sailing": True,
                "sun": {"sunrise": "6:30am", "sunset": "8:15pm", "daylight_hours": 13.75},
            }
        ]

        result = format_json_output(entries)
        parsed = json.loads(result)

        forecast = parsed["forecasts"][0]
        assert "sun" in forecast
        assert forecast["sun"]["sunrise"] == "6:30am"
        assert forecast["sun"]["sunset"] == "8:15pm"

    def test_json_output_includes_best_window(self):
        """Test JSON output includes best window when available."""
        from sailing_conditions.formatters import format_json_output

        entries = [
            {
                "city": "Chicago",
                "city_key": "chicago",
                "label": "Today",
                "rating": 8,
                "wind_line": "—",
                "waves_line": "—",
                "sky_line": "—",
                "sailing": True,
                "best_window": {
                    "start_time": "10am",
                    "end_time": "2pm",
                    "avg_rating": 8.5,
                },
            }
        ]

        result = format_json_output(entries)
        parsed = json.loads(result)

        forecast = parsed["forecasts"][0]
        assert "best_window" in forecast
        assert forecast["best_window"]["start_time"] == "10am"

    def test_json_not_pretty(self):
        """Test JSON output without pretty printing."""
        from sailing_conditions.formatters import format_json_output

        entries = [{"city": "Test", "city_key": "test", "label": "Today", "rating": 5,
                   "wind_line": "—", "waves_line": "—", "sky_line": "—", "sailing": True}]

        result = format_json_output(entries, pretty=False)

        # Not pretty-printed = no newlines
        assert "\n" not in result.strip()


class TestVerboseOutput:
    """Tests for verbose output formatting."""

    def test_verbose_entry_format(self):
        """Test verbose entry formatting."""
        from sailing_conditions.formatters import format_verbose_entry

        entry = {
            "city": "Chicago",
            "prefix": "⛵ ☀",
            "label": "Today",
            "rating": 8,
            "temp_f": 75,
            "wind_line": "N 10–15 kt",
            "waves_line": "2–3 ft",
            "sky_line": "Sunny",
            "sailing": True,
            "rating_breakdown": {
                "base": 10,
                "wind_adj": -1,
                "wind_reason": "light (8kt < 9kt)",
                "wave_adj": 0,
                "wave_reason": "optimal (3ft ≤ 3ft)",
                "sky_adj": 1,
                "sky_reason": "sunny/clear (+1)",
                "raw": 10,
                "final": 8,
            },
        }

        result = format_verbose_entry(entry)

        assert "Chicago" in result
        assert "Rating: 8/10" in result
        assert "Wind: N 10–15 kt" in result
        assert "Rating Breakdown:" in result
        assert "Base score: 10" in result

    def test_verbose_with_sun_times(self):
        """Test verbose output includes sun times."""
        from sailing_conditions.formatters import format_verbose_entry

        entry = {
            "city": "Miami",
            "prefix": "⛵",
            "label": "Today",
            "rating": 7,
            "wind_line": "—",
            "waves_line": "—",
            "sky_line": "—",
            "sun": {"sunrise": "6:45am", "sunset": "8:00pm", "daylight_hours": 13.25},
        }

        result = format_verbose_entry(entry)

        assert "Daylight:" in result
        assert "6:45am" in result
        assert "8:00pm" in result

    def test_verbose_with_best_window(self):
        """Test verbose output includes best window."""
        from sailing_conditions.formatters import format_verbose_entry

        entry = {
            "city": "Chicago",
            "prefix": "⛵",
            "label": "Today",
            "rating": 8,
            "wind_line": "—",
            "waves_line": "—",
            "sky_line": "—",
            "best_window": {
                "start_time": "10am",
                "end_time": "2pm",
                "avg_rating": 8.5,
            },
        }

        result = format_verbose_entry(entry)

        assert "Best Window:" in result
        assert "10am" in result
        assert "2pm" in result


class TestWeekSummary:
    """Tests for week summary formatting."""

    def test_week_summary_format(self):
        """Test week summary formatting."""
        from sailing_conditions.formatters import format_week_summary

        entries = [
            {"prefix": "⛵", "label": "Monday", "rating": 7, "sky_line": "Sunny", "temp_f": 75},
            {"prefix": "⛵", "label": "Tuesday", "rating": 8, "sky_line": "Clear", "temp_f": 78},
            {"prefix": "☁", "label": "Wednesday", "rating": 5, "sky_line": "Cloudy", "temp_f": 70},
        ]

        result = format_week_summary(entries, "Chicago")

        assert "7-Day Forecast" in result
        assert "Chicago" in result
        assert "Monday" in result
        assert "BEST" in result
        assert "Best day: Tuesday" in result

    def test_week_summary_empty(self):
        """Test week summary with no entries."""
        from sailing_conditions.formatters import format_week_summary

        result = format_week_summary([], "Chicago")

        assert "No forecast data" in result


class TestSunTimes:
    """Tests for sun times calculation."""

    def test_sun_times_basic(self):
        """Test basic sun times calculation."""
        from sailing_conditions.fetchers import calculate_sun_times

        # Chicago coordinates
        result = calculate_sun_times(41.8781, -87.6298, dt.date(2025, 6, 21))

        assert result is not None
        assert "sunrise" in result
        assert "sunset" in result
        assert "daylight_hours" in result
        assert result["sunrise"] is not None
        assert result["sunset"] is not None
        # Summer solstice should have long days
        assert result["daylight_hours"] > 14

    def test_sun_times_winter(self):
        """Test sun times in winter (shorter days)."""
        from sailing_conditions.fetchers import calculate_sun_times

        result = calculate_sun_times(41.8781, -87.6298, dt.date(2025, 12, 21))

        assert result is not None
        # Winter solstice should have shorter days
        assert result["daylight_hours"] < 10

    def test_sun_times_defaults_to_today(self):
        """Test sun times defaults to today."""
        from sailing_conditions.fetchers import calculate_sun_times

        result = calculate_sun_times(41.8781, -87.6298)

        assert result is not None


class TestGridPickAllDays:
    """Tests for grid_pick_all_days function."""

    def test_pick_all_days_basic(self):
        """Test picking multiple days."""
        from sailing_conditions.fetchers import grid_pick_all_days

        today = dt.datetime.now().astimezone()
        periods = []
        for i in range(14):  # 2 weeks of data, 2 periods per day
            d = today + dt.timedelta(days=i // 2)
            periods.append({
                "startTime": d.isoformat(),
                "name": "Day" if i % 2 == 0 else "Night",
                "isDaytime": i % 2 == 0,
            })

        result = grid_pick_all_days(periods, num_days=7)

        # Should get up to 7 days
        assert len(result) <= 7
        # Should prefer daytime periods
        for p in result:
            assert p.get("isDaytime", True) is True

    def test_pick_all_days_empty(self):
        """Test with empty periods."""
        from sailing_conditions.fetchers import grid_pick_all_days

        result = grid_pick_all_days(None)
        assert result == []

        result = grid_pick_all_days([])
        assert result == []


class TestAlerts:
    """Tests for alert system."""

    def test_add_alert(self):
        """Test adding an alert."""
        from sailing_conditions.alerts import add_alert, load_alerts, save_alerts

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            with patch("sailing_conditions.alerts.ALERTS_FILE", temp_path):
                alert = add_alert("chicago", min_rating=8)

                assert alert["city_key"] == "chicago"
                assert alert["min_rating"] == 8
                assert "id" in alert

                # Verify it was saved
                alerts = load_alerts()
                assert len(alerts) == 1
                assert alerts[0]["city_key"] == "chicago"
        finally:
            os.unlink(temp_path)

    def test_remove_alert(self):
        """Test removing an alert."""
        from sailing_conditions.alerts import add_alert, remove_alert, load_alerts

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            with patch("sailing_conditions.alerts.ALERTS_FILE", temp_path):
                alert = add_alert("miami", min_rating=7)
                alert_id = alert["id"]

                # Verify it exists
                assert len(load_alerts()) == 1

                # Remove it
                result = remove_alert(alert_id)
                assert result is True

                # Verify it's gone
                assert len(load_alerts()) == 0

                # Try to remove non-existent
                result = remove_alert("fake-id")
                assert result is False
        finally:
            os.unlink(temp_path)

    def test_check_alerts(self):
        """Test checking alerts against forecasts."""
        from sailing_conditions.alerts import add_alert, check_alerts

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            with patch("sailing_conditions.alerts.ALERTS_FILE", temp_path):
                with patch("sailing_conditions.alerts.post_slack"):
                    with patch("sailing_conditions.alerts.send_email_html"):
                        add_alert("chicago", min_rating=7, notify_slack=True)

                        forecasts = [
                            {"city_key": "chicago", "city": "Chicago", "rating": 8, "label": "Today",
                             "wind_line": "—", "waves_line": "—", "sky_line": "—"},
                        ]

                        triggered = check_alerts(forecasts)

                        assert len(triggered) == 1
                        assert triggered[0]["forecast"]["city_key"] == "chicago"
        finally:
            os.unlink(temp_path)

    def test_check_alerts_not_triggered(self):
        """Test alerts not triggered when rating below threshold."""
        from sailing_conditions.alerts import add_alert, check_alerts

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            with patch("sailing_conditions.alerts.ALERTS_FILE", temp_path):
                add_alert("chicago", min_rating=8)

                forecasts = [
                    {"city_key": "chicago", "city": "Chicago", "rating": 6, "label": "Today",
                     "wind_line": "—", "waves_line": "—", "sky_line": "—"},
                ]

                triggered = check_alerts(forecasts)

                assert len(triggered) == 0
        finally:
            os.unlink(temp_path)

    def test_format_alerts_list(self):
        """Test formatting alerts list."""
        from sailing_conditions.alerts import format_alerts_list

        alerts = [
            {
                "id": "alert_123",
                "city_key": "chicago",
                "min_rating": 7,
                "notify_slack": True,
                "notify_email": False,
                "last_triggered": None,
            }
        ]

        result = format_alerts_list(alerts)

        assert "chicago" in result
        assert "rating >= 7" in result
        assert "slack" in result

    def test_format_alerts_list_empty(self):
        """Test formatting empty alerts list."""
        from sailing_conditions.alerts import format_alerts_list

        result = format_alerts_list([])

        assert "No alerts configured" in result


class TestSlackLineWithTemp:
    """Tests for Slack line formatting with temperature."""

    def test_slack_line_with_temperature(self):
        """Test Slack line includes temperature."""
        from sailing_conditions.formatters import format_slack_line_city

        result = format_slack_line_city(
            prefix_emoji="⛵ ☀",
            city="Chicago",
            label="Today",
            rating=8,
            wind_line="N 10–15 kt",
            waves_line="2–3 ft",
            sky_line="Sunny",
            sailing=True,
            suggestion=None,
            temp_f=75,
        )

        assert "75°F" in result

    def test_slack_line_with_sun_times(self):
        """Test Slack line includes sun times."""
        from sailing_conditions.formatters import format_slack_line_city

        result = format_slack_line_city(
            prefix_emoji="⛵ ☀",
            city="Chicago",
            label="Today",
            rating=8,
            wind_line="N 10–15 kt",
            waves_line="2–3 ft",
            sky_line="Sunny",
            sailing=True,
            suggestion=None,
            sun={"sunrise": "6:30am", "sunset": "8:00pm"},
        )

        assert "6:30am" in result
        assert "8:00pm" in result

    def test_slack_line_with_best_window(self):
        """Test Slack line includes best sailing window."""
        from sailing_conditions.formatters import format_slack_line_city

        result = format_slack_line_city(
            prefix_emoji="⛵ ☀",
            city="Chicago",
            label="Today",
            rating=8,
            wind_line="N 10–15 kt",
            waves_line="2–3 ft",
            sky_line="Sunny",
            sailing=True,
            suggestion=None,
            best_window={"start_time": "10am", "end_time": "2pm"},
        )

        assert "Best:" in result
        assert "10am–2pm" in result


class TestPackEnhancements:
    """Tests for enhanced _pack function."""

    def test_pack_with_temperature(self):
        """Test _pack includes temperature conversion."""
        from sailing_conditions.forecast import _pack

        result = _pack(
            city="Test",
            city_key="test",
            label="Today",
            rating=8,
            wind="—",
            waves="—",
            sky="—",
            sailing=True,
            quick="quick",
            prefix="☀",
            temp_f=77,
        )

        assert result["temp_f"] == 77
        assert result["temp_c"] == 25  # (77-32)*5/9 ≈ 25

    def test_pack_with_sun_times(self):
        """Test _pack includes sun times."""
        from sailing_conditions.forecast import _pack

        sun_times = {
            "sunrise": dt.datetime(2025, 6, 15, 6, 30),
            "sunset": dt.datetime(2025, 6, 15, 20, 15),
            "daylight_hours": 13.75,
        }

        result = _pack(
            city="Test",
            city_key="test",
            label="Today",
            rating=8,
            wind="—",
            waves="—",
            sky="—",
            sailing=True,
            quick="quick",
            prefix="☀",
            sun_times=sun_times,
        )

        assert "sun" in result
        assert result["sun"]["sunrise"] == "6:30am"
        assert result["sun"]["sunset"] == "8:15pm"
        assert result["sun"]["daylight_hours"] == 13.75

    def test_pack_with_raw_data(self):
        """Test _pack includes raw wind/wave data."""
        from sailing_conditions.forecast import _pack

        result = _pack(
            city="Test",
            city_key="test",
            label="Today",
            rating=8,
            wind="N 10–15 kt",
            waves="2–4 ft",
            sky="—",
            sailing=True,
            quick="quick",
            prefix="☀",
            wind_raw=(10, 15),
            waves_raw=(2.0, 4.0),
        )

        assert result["wind_kt"] == {"low": 10, "high": 15}
        assert result["waves_ft"] == {"low": 2.0, "high": 4.0}

