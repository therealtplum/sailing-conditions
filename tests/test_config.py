"""Tests for config module."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest


class TestConfigConstants:
    """Tests for configuration constants."""

    def test_conversion_constants(self):
        """Test unit conversion constants are correct."""
        from sailing_conditions.config import MPH_TO_KNOTS, MS_TO_KNOTS

        # 1 mph ≈ 0.869 knots
        assert 0.86 < MPH_TO_KNOTS < 0.88

        # 1 m/s ≈ 1.944 knots
        assert 1.94 < MS_TO_KNOTS < 1.95

    def test_severe_words_is_frozenset(self):
        """Test SEVERE_WORDS is immutable frozenset."""
        from sailing_conditions.config import SEVERE_WORDS

        assert isinstance(SEVERE_WORDS, frozenset)
        assert "gale" in SEVERE_WORDS
        assert "hurricane" in SEVERE_WORDS

    def test_rainy_words_is_frozenset(self):
        """Test RAINY_WORDS is immutable frozenset."""
        from sailing_conditions.config import RAINY_WORDS

        assert isinstance(RAINY_WORDS, frozenset)
        assert "rain" in RAINY_WORDS
        assert "thunder" in RAINY_WORDS

    def test_default_keys(self):
        """Test DEFAULT_KEYS contains expected cities."""
        from sailing_conditions.config import DEFAULT_KEYS

        assert "chicago" in DEFAULT_KEYS
        assert "nyc" in DEFAULT_KEYS
        assert isinstance(DEFAULT_KEYS, list)

    def test_chicago_nearshore_zones(self):
        """Test Chicago nearshore zones are defined."""
        from sailing_conditions.config import CHICAGO_NEARSHORE

        assert isinstance(CHICAGO_NEARSHORE, list)
        assert len(CHICAGO_NEARSHORE) > 0
        assert all("lmz" in zone for zone in CHICAGO_NEARSHORE)

    def test_ndbc_station(self):
        """Test NDBC station is defined."""
        from sailing_conditions.config import NDBC_STATION

        assert NDBC_STATION == "CHII2"

    def test_tgftp_root_url(self):
        """Test TGFTP root URL."""
        from sailing_conditions.config import TGFTP_ROOT

        assert "tgftp.nws.noaa.gov" in TGFTP_ROOT
        assert TGFTP_ROOT.startswith("https://")


class TestUserAgentConfig:
    """Tests for User-Agent configuration."""

    def test_default_user_agent(self):
        """Test default User-Agent string."""
        # Import fresh to get default
        import importlib
        import sailing_conditions.config as config_module
        
        # Check the format
        assert "SailingConditions" in config_module.NWS_UA
        assert "contact:" in config_module.NWS_UA

    @patch.dict(os.environ, {"SAILING_CONDITIONS_CONTACT": "test@example.com"})
    def test_custom_contact_email(self):
        """Test custom contact email via environment variable."""
        # Need to reimport to pick up env var
        import importlib
        import sailing_conditions.config as config_module
        
        importlib.reload(config_module)
        
        assert "test@example.com" in config_module.NWS_UA

    def test_rating_constants_defined(self):
        """Test rating algorithm constants are defined."""
        from sailing_conditions.config import (
            WAVE_DANGEROUS_HIGH,
            WAVE_OPTIMAL_HIGH,
            WAVE_VERY_HIGH,
            WIND_DANGEROUS_HIGH,
            WIND_OPTIMAL_HIGH,
            WIND_OPTIMAL_LOW,
            WIND_VERY_HIGH,
        )

        # Wind constants should be in reasonable ranges
        assert WIND_OPTIMAL_LOW < WIND_OPTIMAL_HIGH
        assert WIND_OPTIMAL_HIGH < WIND_VERY_HIGH
        assert WIND_VERY_HIGH < WIND_DANGEROUS_HIGH

        # Wave constants should be in reasonable ranges
        assert WAVE_OPTIMAL_HIGH < WAVE_VERY_HIGH
        assert WAVE_VERY_HIGH < WAVE_DANGEROUS_HIGH

