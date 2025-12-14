"""Tests for parsers module."""
import pytest
from sailing_conditions.parsers import (
    parse_wind,
    parse_waves,
    parse_sky,
    compute_rating,
    extract_day_blurb,
    normalize_heading,
)


def test_parse_wind():
    """Test wind parsing."""
    # Test with direction and range
    wdir, wrng = parse_wind("N 10 to 15 kt")
    assert wdir == "N"
    assert wrng == (10, 15)
    
    # Test with single speed
    wdir, wrng = parse_wind("15 kt")
    assert wrng == (15, 15)
    
    # Test with no wind info
    wdir, wrng = parse_wind("sunny")
    assert wrng is None


def test_parse_waves():
    """Test wave parsing."""
    # Test range
    waves = parse_waves("waves 2 to 4 ft")
    assert waves == (2.0, 4.0)
    
    # Test single value
    waves = parse_waves("seas 3 ft")
    assert waves == (3.0, 3.0)
    
    # Test no waves
    waves = parse_waves("sunny")
    assert waves is None


def test_parse_sky():
    """Test sky parsing."""
    assert parse_sky("sunny") == "sunny"
    assert parse_sky("partly cloudy") == "partly cloudy"
    assert parse_sky("no weather info") is None


def test_compute_rating():
    """Test rating computation."""
    # Good conditions
    assert compute_rating((10, 15), (1, 2), "sunny") >= 7
    
    # Poor conditions
    assert compute_rating((25, 30), (5, 7), "storms") <= 4
    
    # No data
    assert compute_rating(None, None, None) == 5


def test_normalize_heading():
    """Test heading normalization."""
    assert normalize_heading("  today  ") == "TODAY"
    assert normalize_heading("rest   of   today") == "REST OF TODAY"


def test_extract_day_blurb():
    """Test day blurb extraction."""
    text = "TODAY... Wind N 10-15 kt. Waves 2-3 ft. Sunny."
    result = extract_day_blurb(text, "TODAY")
    assert result is not None
    assert "TODAY" in result

