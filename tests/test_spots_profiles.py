"""Spot registry and boat profiles — the data-driven half of the tool."""

from __future__ import annotations

import pytest

from sailing_conditions.models import Spot
from sailing_conditions.profiles import (
    BUILTIN_PROFILES,
    WindBand,
    get_profile,
    profile_from_mapping,
)
from sailing_conditions.spots import SpotRegistry, UnknownSpot, builtin_spots, spot_from_mapping


def test_builtin_spots_load_and_are_sane():
    spots = builtin_spots()
    assert len(spots) >= 15
    for key, spot in spots.items():
        assert spot.key == key
        assert -90 <= spot.lat <= 90 and -180 <= spot.lon <= 180
        assert spot.name and spot.region
        assert spot.blurb, f"{key} has no description"


def test_us_only_coordinates():
    """Every built-in must sit inside NWS coverage, or its grid lookup 404s."""
    for spot in builtin_spots().values():
        assert 18 <= spot.lat <= 72, spot.key
        assert -180 <= spot.lon <= -66, spot.key


def test_registry_lookup_is_case_insensitive():
    registry = SpotRegistry()
    assert registry.get("CHICAGO").key == "chicago"
    assert registry.get(" chicago ").key == "chicago"


def test_unknown_spot_suggests_a_correction():
    with pytest.raises(UnknownSpot) as exc:
        SpotRegistry().get("chigago")
    assert "chicago" in str(exc.value)
    assert exc.value.suggestions == ("chicago",)


def test_unknown_spot_without_a_close_match():
    with pytest.raises(UnknownSpot) as exc:
        SpotRegistry().get("zzzzz")
    assert "sail spots" in str(exc.value)


def test_resolve_preserves_order_and_deduplicates():
    spots = SpotRegistry().resolve(["miami", "chicago", "miami"])
    assert [s.key for s in spots] == ["miami", "chicago"]


def test_user_spots_override_builtins():
    mine = Spot(key="chicago", name="My Dock", lat=41.0, lon=-87.0)
    registry = SpotRegistry().merged({"chicago": mine})
    assert registry.get("chicago").name == "My Dock"
    assert len(registry) == len(SpotRegistry())


def test_tags():
    assert {s.key for s in SpotRegistry().tagged("great-lakes")} >= {"chicago", "milwaukee", "cleveland"}


def test_spot_from_mapping_requires_coordinates():
    with pytest.raises(ValueError, match="lat and lon"):
        spot_from_mapping("bad", {"name": "Nowhere"})


def test_spot_from_mapping_rejects_impossible_coordinates():
    with pytest.raises(ValueError, match="out of range"):
        spot_from_mapping("bad", {"lat": 91, "lon": 0})


def test_spot_title():
    spot = Spot(key="k", name="Belmont Harbor", lat=0, lon=0, region="Chicago, IL")
    assert spot.title == "Belmont Harbor, Chicago, IL"


def test_wind_band_must_be_ordered():
    with pytest.raises(ValueError, match="non-decreasing"):
        WindBand(min=10, ideal_lo=5, ideal_hi=20, max=30)


def test_builtin_profiles_are_coherent():
    for key, profile in BUILTIN_PROFILES.items():
        assert profile.key == key
        assert profile.wave_ok_ft < profile.wave_max_ft
        assert profile.gust_ratio_ok < profile.gust_ratio_max
        assert profile.comfort_min_f < profile.comfort_f[0] < profile.comfort_f[1] < profile.comfort_max_f
        assert profile.summary


def test_profiles_are_ordered_by_appetite_for_breeze():
    """A beginner's ceiling should sit below a heavy-air sailor's floor-ish."""
    assert BUILTIN_PROFILES["beginner"].wind.max < BUILTIN_PROFILES["heavy_air"].wind.ideal_hi


def test_get_profile_reports_the_valid_keys():
    with pytest.raises(KeyError) as exc:
        get_profile("yacht")
    assert "keelboat" in str(exc.value)


def test_user_profile_inherits_from_a_builtin():
    profile = profile_from_mapping("my_j24", {"name": "My J/24", "wind": {"ideal_hi": 24}})
    assert profile.name == "My J/24"
    assert profile.wind.ideal_hi == 24
    assert profile.wind.min == BUILTIN_PROFILES["keelboat"].wind.min
    assert profile.wave_max_ft == BUILTIN_PROFILES["keelboat"].wave_max_ft


def test_user_profile_can_extend_any_builtin():
    profile = profile_from_mapping("laser", {"extends": "dinghy", "wave_max_ft": 3.0})
    assert profile.wind.ideal_hi == BUILTIN_PROFILES["dinghy"].wind.ideal_hi
    assert profile.wave_max_ft == 3.0


def test_user_profile_weights_merge():
    profile = profile_from_mapping("picky", {"weights": {"sea": 5.0}})
    assert profile.weight("sea") == 5.0
    assert profile.weight("wind") == BUILTIN_PROFILES["keelboat"].weight("wind")


def test_get_profile_prefers_user_definitions():
    custom = profile_from_mapping("keelboat", {"name": "Mine"})
    assert get_profile("keelboat", {"keelboat": custom}).name == "Mine"
