"""Tests for cities module."""
from __future__ import annotations

import pytest

from sailing_conditions.cities import CITIES


class TestCitiesRegistry:
    """Tests for CITIES registry."""

    def test_cities_is_dict(self):
        """Test CITIES is a dictionary."""
        assert isinstance(CITIES, dict)
        assert len(CITIES) > 0

    def test_required_fields(self):
        """Test all cities have required fields."""
        required_fields = {"label", "type", "lat", "lon", "sailing"}

        for key, city in CITIES.items():
            for field in required_fields:
                assert field in city, f"City '{key}' missing required field '{field}'"

    def test_city_types_valid(self):
        """Test city types are valid."""
        valid_types = {"marine", "grid"}

        for key, city in CITIES.items():
            assert city["type"] in valid_types, f"City '{key}' has invalid type '{city['type']}'"

    def test_coordinates_valid(self):
        """Test coordinates are in valid ranges."""
        for key, city in CITIES.items():
            lat, lon = city["lat"], city["lon"]
            assert -90 <= lat <= 90, f"City '{key}' has invalid latitude {lat}"
            assert -180 <= lon <= 180, f"City '{key}' has invalid longitude {lon}"

    def test_marine_cities_have_zones(self):
        """Test marine cities have marine_zones defined."""
        for key, city in CITIES.items():
            if city["type"] == "marine":
                assert "marine_zones" in city, f"Marine city '{key}' missing marine_zones"
                assert len(city["marine_zones"]) > 0, f"Marine city '{key}' has empty marine_zones"

    def test_sailing_is_boolean(self):
        """Test sailing field is boolean."""
        for key, city in CITIES.items():
            assert isinstance(city["sailing"], bool), f"City '{key}' sailing field is not boolean"

    def test_original_five_cities(self):
        """Test original five cities are present."""
        original_five = ["chicago", "philly", "kc", "slc", "nyc"]
        for city in original_five:
            assert city in CITIES, f"Original city '{city}' not in CITIES"

    def test_chicago_config(self):
        """Test Chicago configuration."""
        assert "chicago" in CITIES
        chicago = CITIES["chicago"]
        assert chicago["label"] == "Chicago"
        assert chicago["type"] == "marine"
        assert chicago["sailing"] is True
        assert "marine_zones" in chicago

    def test_non_sailing_cities(self):
        """Test non-sailing cities exist."""
        non_sailing = [key for key, city in CITIES.items() if not city["sailing"]]
        assert len(non_sailing) > 0, "Should have at least one non-sailing city"
        assert "philly" in non_sailing
        assert "kc" in non_sailing

    def test_labels_are_strings(self):
        """Test all labels are non-empty strings."""
        for key, city in CITIES.items():
            assert isinstance(city["label"], str), f"City '{key}' label is not a string"
            assert len(city["label"]) > 0, f"City '{key}' has empty label"

    def test_marine_zones_format(self):
        """Test marine zones are in expected format."""
        for key, city in CITIES.items():
            if city["type"] == "marine" and "marine_zones" in city:
                for zone in city["marine_zones"]:
                    assert zone.startswith("marine/"), f"City '{key}' has invalid zone format: {zone}"
                    assert zone.endswith(".txt"), f"City '{key}' zone should end with .txt: {zone}"

    def test_popular_sailing_cities(self):
        """Test popular sailing cities are included."""
        sailing_cities = ["miami", "sf", "boston", "seattle", "sd", "la"]
        for city in sailing_cities:
            assert city in CITIES, f"Popular sailing city '{city}' not in CITIES"
            assert CITIES[city]["sailing"] is True

    def test_city_count(self):
        """Test we have a reasonable number of cities."""
        assert len(CITIES) >= 20, "Should have at least 20 cities"

