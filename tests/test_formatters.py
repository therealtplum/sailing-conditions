"""Tests for formatters module."""
from __future__ import annotations

import pytest

from sailing_conditions.formatters import build_email_html, format_slack_line_city


class TestFormatSlackLineCity:
    """Tests for format_slack_line_city function."""

    def test_sailing_city_format(self):
        """Test format for sailing city."""
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
        )
        assert "⛵ ☀" in result
        assert "Chicago" in result
        assert "8/10" in result
        assert "N 10–15 kt" in result
        assert "2–3 ft" in result
        assert "Sunny" in result

    def test_non_sailing_city_format(self):
        """Test format for non-sailing city."""
        result = format_slack_line_city(
            prefix_emoji="☀",
            city="Philadelphia",
            label="Today",
            rating=7,
            wind_line="SW 5–10 kt",
            waves_line="—",
            sky_line="Sunny",
            sailing=False,
            suggestion="hit a park picnic",
        )
        assert "☀" in result
        assert "Philadelphia" in result
        assert "Sunny" in result
        assert "hit a park picnic" in result
        # Non-sailing should not have wind/waves/rating in the same format
        assert "7/10" not in result

    def test_non_sailing_no_suggestion(self):
        """Test non-sailing city without suggestion."""
        result = format_slack_line_city(
            prefix_emoji="🌥",
            city="Kansas City",
            label="Today",
            rating=5,
            wind_line="—",
            waves_line="—",
            sky_line="Cloudy",
            sailing=False,
            suggestion=None,
        )
        assert "Kansas City" in result
        assert "Cloudy" in result

    def test_no_trailing_whitespace(self):
        """Test that result has no trailing whitespace."""
        result = format_slack_line_city(
            prefix_emoji="☀",
            city="Test City",
            label="Today",
            rating=5,
            wind_line="—",
            waves_line="—",
            sky_line="Clear",
            sailing=False,
            suggestion="",  # Empty suggestion
        )
        assert result == result.rstrip()


class TestBuildEmailHtml:
    """Tests for build_email_html function."""

    def test_basic_html_structure(self):
        """Test basic HTML structure."""
        entries = [
            {
                "prefix": "⛵ ☀",
                "city": "Chicago",
                "label": "Today",
                "rating": 8,
                "wind_line": "N 10–15 kt",
                "waves_line": "2–3 ft",
                "sky_line": "Sunny",
            }
        ]
        html = build_email_html(entries, "Mon Jan 6, 2025")

        assert "<!doctype html>" in html
        assert "<html>" in html
        assert "</html>" in html
        assert "Chicago" in html
        assert "8/10" in html
        assert "Mon Jan 6, 2025" in html

    def test_rating_colors(self):
        """Test different rating colors."""
        # High rating - green
        entries = [{"prefix": "☀", "city": "A", "label": "Today", "rating": 9, "wind_line": "—", "waves_line": "—", "sky_line": "—"}]
        html = build_email_html(entries, "date")
        assert "#16a34a" in html  # Green

        # Medium rating - yellow
        entries = [{"prefix": "☀", "city": "A", "label": "Today", "rating": 6, "wind_line": "—", "waves_line": "—", "sky_line": "—"}]
        html = build_email_html(entries, "date")
        assert "#eab308" in html  # Yellow

        # Low rating - red
        entries = [{"prefix": "☀", "city": "A", "label": "Today", "rating": 3, "wind_line": "—", "waves_line": "—", "sky_line": "—"}]
        html = build_email_html(entries, "date")
        assert "#dc2626" in html  # Red

    def test_empty_entries(self):
        """Test with no entries."""
        html = build_email_html([], "Mon Jan 6, 2025")
        assert "No data." in html

    def test_multiple_entries(self):
        """Test with multiple entries."""
        entries = [
            {"prefix": "⛵ ☀", "city": "Chicago", "label": "Today", "rating": 8, "wind_line": "N 10–15 kt", "waves_line": "2–3 ft", "sky_line": "Sunny"},
            {"prefix": "⛵ 🌥", "city": "NYC", "label": "Today", "rating": 6, "wind_line": "S 8–12 kt", "waves_line": "1–2 ft", "sky_line": "Cloudy"},
        ]
        html = build_email_html(entries, "Mon Jan 6, 2025")

        assert "Chicago" in html
        assert "NYC" in html
        assert html.count("<tr>") >= 3  # Header row + 2 data rows

    def test_table_headers(self):
        """Test that table headers are present."""
        entries = [{"prefix": "☀", "city": "Test", "label": "Today", "rating": 5, "wind_line": "—", "waves_line": "—", "sky_line": "—"}]
        html = build_email_html(entries, "date")

        assert "City" in html
        assert "Day" in html
        assert "Rating" in html
        assert "Wind" in html
        assert "Waves" in html
        assert "Sky" in html

