"""Tests for fetchers module."""
from __future__ import annotations

import datetime as dt
from unittest.mock import Mock, patch

import pytest

from sailing_conditions.fetchers import (
    fetch_grid_periods,
    fetch_ndbc_latest,
    fetch_tgftp_text,
    grid_pick_day,
    http_get,
)


class TestHttpGet:
    """Tests for http_get function."""

    @patch("sailing_conditions.fetchers.requests.get")
    def test_successful_request(self, mock_get):
        """Test successful HTTP request."""
        mock_get.return_value = Mock(status_code=200, text="Success")
        response = http_get("http://example.com")
        assert response.status_code == 200
        assert mock_get.call_count == 1

    @patch("sailing_conditions.fetchers.requests.get")
    def test_retry_on_failure(self, mock_get):
        """Test HTTP get with retry logic."""
        import requests

        # Simulate failure then success
        mock_get.side_effect = [
            requests.RequestException("Connection error"),
            Mock(status_code=200, text="Success"),
        ]

        # Should retry and succeed
        response = http_get("http://example.com", max_retries=2, backoff=0.01)
        assert response.status_code == 200
        assert mock_get.call_count == 2

    @patch("sailing_conditions.fetchers.requests.get")
    def test_all_retries_fail(self, mock_get):
        """Test when all retries fail."""
        import requests

        mock_get.side_effect = requests.RequestException("Connection error")

        with pytest.raises(requests.RequestException):
            http_get("http://example.com", max_retries=2, backoff=0.01)

        assert mock_get.call_count == 2

    @patch("sailing_conditions.fetchers.requests.get")
    def test_custom_timeout(self, mock_get):
        """Test custom timeout parameter."""
        mock_get.return_value = Mock(status_code=200)
        http_get("http://example.com", timeout=30)
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["timeout"] == 30


class TestFetchTgftpText:
    """Tests for fetch_tgftp_text function."""

    @patch("sailing_conditions.fetchers.http_get")
    def test_successful_fetch(self, mock_http_get):
        """Test successful TGFTP text fetching."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "Test forecast data"
        mock_http_get.return_value = mock_response

        result = fetch_tgftp_text("marine/test.txt")
        assert result == "Test forecast data"

    @patch("sailing_conditions.fetchers.http_get")
    def test_empty_response(self, mock_http_get):
        """Test with empty response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "   "  # whitespace only
        mock_http_get.return_value = mock_response

        result = fetch_tgftp_text("marine/test.txt")
        assert result is None

    @patch("sailing_conditions.fetchers.http_get")
    def test_failed_fetch(self, mock_http_get):
        """Test failed fetch returns None."""
        mock_http_get.side_effect = Exception("Network error")

        result = fetch_tgftp_text("marine/test.txt")
        assert result is None


class TestFetchGridPeriods:
    """Tests for fetch_grid_periods function."""

    @patch("sailing_conditions.fetchers.http_get")
    def test_successful_fetch(self, mock_http_get):
        """Test successful grid periods fetch."""
        # Mock the points API response
        points_response = Mock()
        points_response.status_code = 200
        points_response.json.return_value = {
            "properties": {"forecast": "https://api.weather.gov/forecast/123"}
        }

        # Mock the forecast API response
        forecast_response = Mock()
        forecast_response.status_code = 200
        forecast_response.json.return_value = {
            "properties": {
                "periods": [
                    {"name": "Today", "temperature": 72},
                    {"name": "Tonight", "temperature": 55},
                ]
            }
        }

        mock_http_get.side_effect = [points_response, forecast_response]

        result = fetch_grid_periods(41.9, -87.6)
        assert result is not None
        assert len(result) == 2
        assert result[0]["name"] == "Today"

    @patch("sailing_conditions.fetchers.http_get")
    def test_invalid_coordinates(self, mock_http_get):
        """Test with invalid coordinates."""
        result = fetch_grid_periods(999, 999)  # Invalid coordinates
        assert result is None
        mock_http_get.assert_not_called()

    @patch("sailing_conditions.fetchers.http_get")
    def test_api_error(self, mock_http_get):
        """Test API error handling."""
        import requests

        mock_http_get.side_effect = requests.RequestException("API Error")

        result = fetch_grid_periods(41.9, -87.6)
        assert result is None


class TestGridPickDay:
    """Tests for grid_pick_day function."""

    def test_pick_today(self):
        """Test picking today's forecast."""
        now = dt.datetime.now().astimezone()
        periods = [
            {
                "name": "Today",
                "startTime": now.isoformat(),
            },
            {
                "name": "Tonight",
                "startTime": (now + dt.timedelta(hours=12)).isoformat(),
            },
        ]

        result = grid_pick_day(periods, "TODAY")
        assert result is not None
        assert result["name"] == "Today"

    def test_pick_tomorrow(self):
        """Test picking tomorrow's forecast."""
        now = dt.datetime.now().astimezone()
        tomorrow = now + dt.timedelta(days=1)
        periods = [
            {
                "name": "Today",
                "startTime": now.isoformat(),
            },
            {
                "name": "Tomorrow",
                "startTime": tomorrow.replace(hour=6).isoformat(),
            },
        ]

        result = grid_pick_day(periods, "TOMORROW")
        assert result is not None
        assert result["name"] == "Tomorrow"

    def test_empty_periods(self):
        """Test with empty periods list."""
        result = grid_pick_day([], "TODAY")
        assert result is None

    def test_none_periods(self):
        """Test with None periods."""
        result = grid_pick_day(None, "TODAY")
        assert result is None

    def test_weekend_picking(self):
        """Test picking weekend day."""
        now = dt.datetime.now().astimezone()
        # Find next Saturday
        days_until_saturday = (5 - now.weekday()) % 7
        saturday = now + dt.timedelta(days=days_until_saturday)

        periods = [
            {
                "name": "Today",
                "startTime": now.isoformat(),
            },
            {
                "name": "Saturday",
                "startTime": saturday.replace(hour=6).isoformat(),
            },
        ]

        result = grid_pick_day(periods, "SATURDAY")
        assert result is not None


class TestFetchNdbcLatest:
    """Tests for fetch_ndbc_latest function."""

    @patch("sailing_conditions.fetchers.http_get")
    def test_successful_fetch(self, mock_http_get):
        """Test successful NDBC data fetch."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """#header line
YY  MM DD hh mm WDIR WSPD GST  WVHT   DPD   APD MWD   PRES  ATMP  WTMP  DEWP  VIS PTDY  TIDE
25  01 07 12 00  180  5.0  6.5   MM    MM    MM  MM 1013.0    MM    MM    MM   MM   MM    MM"""
        mock_http_get.return_value = mock_response

        result = fetch_ndbc_latest("CHII2")
        assert result is not None
        assert result["wdir_deg"] == 180
        assert result["wspd_kt"] is not None  # Converted from m/s

    @patch("sailing_conditions.fetchers.http_get")
    def test_missing_required_field(self, mock_http_get):
        """Test with missing required field."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """#header line
YY  MM DD hh mm WSPD GST
25  01 07 12 00  5.0  6.5"""  # Missing WDIR
        mock_http_get.return_value = mock_response

        result = fetch_ndbc_latest("CHII2")
        assert result is None

    @patch("sailing_conditions.fetchers.http_get")
    def test_fetch_error(self, mock_http_get):
        """Test network error handling."""
        import requests

        mock_http_get.side_effect = requests.RequestException("Network error")

        result = fetch_ndbc_latest("CHII2")
        assert result is None

    @patch("sailing_conditions.fetchers.http_get")
    def test_insufficient_data(self, mock_http_get):
        """Test with insufficient data lines."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "#header only"
        mock_http_get.return_value = mock_response

        result = fetch_ndbc_latest("CHII2")
        assert result is None
