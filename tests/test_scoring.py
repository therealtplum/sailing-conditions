"""The scoring model.

These tests are mostly about *properties* rather than magic numbers: more
wind up to the sweet spot is better, past it is worse, missing data is not
a penalty, and a veto beats everything. Pinning exact scores would make the
model impossible to tune; pinning its behavior makes tuning safe.
"""

from __future__ import annotations

import datetime as dt

import pytest

from sailing_conditions.models import Hazard, Verdict
from sailing_conditions.profiles import BUILTIN_PROFILES
from sailing_conditions.scoring import plateau, ramp, rescale, score_hour, score_hours
from tests.conftest import CHICAGO, make_hour


def test_ramp_is_clamped_and_directional():
    assert ramp(5, 0, 10) == pytest.approx(0.5)
    assert ramp(-5, 0, 10) == 0.0
    assert ramp(50, 0, 10) == 1.0
    # Descending ramp: 1 at 4, 0 at 10.
    assert ramp(7, 10, 4) == pytest.approx(0.5)


def test_ramp_with_degenerate_bounds():
    assert ramp(5, 5, 5) == 1.0
    assert ramp(4, 5, 5) == 0.0


def test_plateau_shape():
    assert plateau(0, 4, 10, 20, 30) == 0.0
    assert plateau(7, 4, 10, 20, 30) == pytest.approx(0.5)
    assert plateau(15, 4, 10, 20, 30) == 1.0
    assert plateau(25, 4, 10, 20, 30) == pytest.approx(0.5)
    assert plateau(35, 4, 10, 20, 30) == 0.0


def test_rescale_compresses_into_floor_range():
    assert rescale(0.0, 0.25) == pytest.approx(0.25)
    assert rescale(1.0, 0.25) == pytest.approx(1.0)


def test_ideal_conditions_score_high(keelboat):
    score = score_hour(make_hour(wind_kt=14, wave_ft=1.5, sky_pct=5, precip_pct=0), keelboat)
    assert score.value >= 9.0
    assert score.verdict in (Verdict.EPIC, Verdict.GOOD)
    assert not score.vetoed


def test_glassy_calm_is_not_sailing(keelboat):
    score = score_hour(make_hour(wind_kt=1), keelboat)
    assert score.value < 2.0
    assert "glassy" in dict((f.name, f.note) for f in score.factors)["wind"]


def test_score_rises_then_falls_with_wind(keelboat):
    values = [score_hour(make_hour(wind_kt=kt), keelboat).value for kt in (2, 6, 10, 15, 20)]
    assert values == sorted(values), "score should climb toward the sweet spot"
    assert score_hour(make_hour(wind_kt=15), keelboat).value > score_hour(make_hour(wind_kt=27), keelboat).value


def test_profiles_disagree_about_the_same_hour():
    hour = make_hour(wind_kt=22, gust_kt=26, wave_ft=3.0)
    beginner = score_hour(hour, BUILTIN_PROFILES["beginner"]).value
    heavy_air = score_hour(hour, BUILTIN_PROFILES["heavy_air"]).value
    assert heavy_air > beginner + 3, "a heavy-air boat should love what scares a beginner"


def test_missing_data_is_not_a_penalty(keelboat):
    """An inland spot with no wave grid must not be punished for it."""
    with_waves = score_hour(make_hour(wind_kt=12, wave_ft=1.0), keelboat)
    without_waves = score_hour(make_hour(wind_kt=12, wave_ft=None), keelboat)
    assert {f.name for f in with_waves.factors} - {f.name for f in without_waves.factors} == {"sea"}
    assert without_waves.value == pytest.approx(with_waves.value, abs=0.35)


def test_one_bad_factor_drags_the_whole_score_down(keelboat):
    """The geometric mean is the point: sunshine does not fix 6 ft seas."""
    lovely = score_hour(make_hour(wind_kt=14, wave_ft=1.0, sky_pct=0), keelboat)
    lumpy = score_hour(make_hour(wind_kt=14, wave_ft=6.5, sky_pct=0), keelboat)
    assert lumpy.value < lovely.value / 2


def test_seas_past_the_comfort_limit_cap_the_score_without_a_hard_veto(keelboat):
    """Big seas are the skipper's call, unlike lightning."""
    score = score_hour(make_hour(wind_kt=14, wave_ft=6.0), keelboat)
    assert score.value <= 3.0
    assert score.vetoes and not score.vetoed


def test_gusts_are_scored_on_ratio_not_absolute_speed(keelboat):
    steady = score_hour(make_hour(wind_kt=20, gust_kt=23), keelboat)
    squirrelly = score_hour(make_hour(wind_kt=10, gust_kt=23), keelboat)
    assert squirrelly.value < steady.value


def test_thunder_is_a_hard_veto(keelboat):
    score = score_hour(make_hour(wind_kt=13, thunder_pct=45), keelboat)
    assert score.vetoed
    assert score.verdict is Verdict.NO_GO
    assert score.value <= 1.0
    assert "lightning" in score.vetoes[0].reason


def test_thunder_veto_threshold_follows_the_profile():
    hour = make_hour(wind_kt=12, thunder_pct=25)
    assert score_hour(hour, BUILTIN_PROFILES["cruiser"]).vetoed  # threshold 20
    assert not score_hour(hour, BUILTIN_PROFILES["keelboat"]).vetoed  # threshold 30


def test_veto_preserves_the_underlying_quality(keelboat):
    """--explain should be able to say "great conditions, but lightning"."""
    score = score_hour(make_hour(wind_kt=13, wave_ft=1.0, thunder_pct=60), keelboat)
    wind_factor = next(f for f in score.factors if f.name == "wind")
    assert wind_factor.score == pytest.approx(1.0)
    assert score.value <= 1.0


def test_critical_hazard_forces_no_go(keelboat):
    hazard = Hazard(event="Special Marine Warning", severity="Severe", headline="SMW in effect")
    score = score_hour(make_hour(wind_kt=13), keelboat, [hazard])
    assert score.verdict is Verdict.NO_GO
    assert score.vetoed


def test_advisory_caps_without_forcing_no_go(keelboat):
    hazard = Hazard(event="Small Craft Advisory", severity="Moderate", headline="SCA in effect")
    score = score_hour(make_hour(wind_kt=13, wave_ft=1.0), keelboat, [hazard])
    assert score.value <= 4.5
    assert not score.vetoed
    assert score.verdict is not Verdict.NO_GO


def test_hazard_only_applies_inside_its_window(keelboat):
    hazard = Hazard(
        event="Special Marine Warning",
        severity="Severe",
        headline="SMW",
        onset=dt.datetime(2026, 8, 15, 14, tzinfo=CHICAGO),
        ends=dt.datetime(2026, 8, 15, 16, tzinfo=CHICAGO),
    )
    assert score_hour(make_hour(15), keelboat, [hazard]).vetoed
    assert not score_hour(make_hour(11), keelboat, [hazard]).vetoed
    assert not score_hour(make_hour(18), keelboat, [hazard]).vetoed


def test_unknown_hazard_events_are_ignored(keelboat):
    hazard = Hazard(event="Air Quality Alert", severity="Minor", headline="hazy")
    assert not score_hour(make_hour(wind_kt=13), keelboat, [hazard]).vetoed


def test_limiting_factor_identifies_the_problem(keelboat):
    score = score_hour(make_hour(wind_kt=13, wave_ft=6.0, sky_pct=10), keelboat)
    assert score.limiting_factor is not None
    assert score.limiting_factor.name == "sea"


def test_limiting_factor_weighs_importance_not_just_lowness(keelboat):
    """A mediocre wind beats a dismal sky: one ruins the day, the other doesn't."""
    score = score_hour(make_hour(wind_kt=8.5, sky_pct=100, wave_ft=1.0), keelboat)
    scores = {f.name: f.score for f in score.factors}
    assert scores["sky"] < scores["wind"], "the sky factor really is the lower number"
    assert score.limiting_factor.name == "wind"


def test_every_factor_explains_itself(keelboat):
    score = score_hour(make_hour(wind_kt=13, gust_kt=18, wave_ft=2.0), keelboat)
    assert {f.name for f in score.factors} == {"wind", "gust", "sea", "precip", "comfort", "sky"}
    for factor in score.factors:
        assert factor.note, f"{factor.name} has no explanation"
        assert 0.0 <= factor.score <= 1.0


def test_scores_are_bounded(keelboat):
    for kt in range(0, 60, 3):
        value = score_hour(make_hour(wind_kt=kt), keelboat).value
        assert 0.0 <= value <= 10.0


def test_score_hours_maps_over_a_sequence(keelboat):
    hours = [make_hour(h, wind_kt=12) for h in range(8, 12)]
    assert len(score_hours(hours, keelboat)) == 4
