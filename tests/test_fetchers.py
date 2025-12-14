"""Tests for fetchers module."""
import pytest
from unittest.mock import patch, Mock
from sailing_conditions.fetchers import (
    http_get,
    fetch_tgftp_text,
    fetch_grid_periods,
    grid_pick_day,
)


@patch('sailing_conditions.fetchers.requests.get')
def test_http_get_retry(mock_get):
    """Test HTTP get with retry logic."""
    # Simulate failure then success
    mock_get.side_effect = [
        Exception("Connection error"),
        Mock(status_code=200, text="Success")
    ]
    
    # Should retry and succeed
    response = http_get("http://example.com", max_retries=2, backoff=0.1)
    assert response.status_code == 200
    assert mock_get.call_count == 2


@patch('sailing_conditions.fetchers.http_get')
def test_fetch_tgftp_text(mock_http_get):
    """Test TGFTP text fetching."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = "Test forecast"
    mock_http_get.return_value = mock_response
    
    result = fetch_tgftp_text("marine/test.txt")
    assert result == "Test forecast"


def test_grid_pick_day():
    """Test grid day picking."""
    import datetime as dt
    
    periods = [
        {
            "name": "Today",
            "startTime": dt.datetime.now().isoformat(),
        },
        {
            "name": "Tonight",
            "startTime": (dt.datetime.now() + dt.timedelta(hours=12)).isoformat(),
        },
    ]
    
    result = grid_pick_day(periods, "TODAY")
    assert result is not None
    assert result["name"] == "Today"

