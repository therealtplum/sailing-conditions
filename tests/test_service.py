"""Report assembly: fetch, score, group, annotate."""

from __future__ import annotations

import datetime as dt
from dataclasses import replace

import pytest

from sailing_conditions.service import Forecaster
from sailing_conditions.sources.ndbc import NdbcClient
from sailing_conditions.sources.nws import NwsClient
from tests.conftest import FIXTURE_NOW, FixtureFetcher


def build(fetcher: FixtureFetcher, *, live: bool = True) -> Forecaster:
    return Forecaster(nws=NwsClient(fetcher), ndbc=NdbcClient(fetcher) if live else None)


def test_report_is_grouped_into_local_days(fetcher, spot, keelboat):
    report = build(fetcher).report(spot, keelboat, days=2, now=FIXTURE_NOW)
    assert report.timezone == "America/Chicago"
    assert [day.date for day in report.days] == [dt.date(2026, 8, 15), dt.date(2026, 8, 16)]
    assert all(hour.time.date() == day.date for day in report.days for hour in day.hours)


def test_elapsed_hours_are_dropped(fetcher, spot, keelboat):
    """At 4pm, nobody needs to be told the morning was lovely."""
    afternoon = dt.datetime(2026, 8, 15, 21, 5, tzinfo=dt.UTC)  # 4:05pm in Chicago
    report = build(fetcher).report(spot, keelboat, days=1, now=afternoon)
    hours = report.days[0].hours
    assert hours, "the rest of the day is still forecast"
    assert hours[0].time.hour == 16
    assert all(window.start >= hours[0].time for window in report.days[0].windows)


def test_hours_are_scored_and_flagged_for_daylight(fetcher, spot, keelboat):
    day = build(fetcher).report(spot, keelboat, days=1, now=FIXTURE_NOW).days[0]
    assert day.hours
    assert all(0 <= hour.value <= 10 for hour in day.hours)
    assert any(hour.daylight for hour in day.hours)
    night = [hour for hour in day.hours if not hour.daylight]
    assert all(hour.time.hour < 7 or hour.time.hour > 19 for hour in night)


def test_day_score_uses_the_best_three_daylight_hours(fetcher, spot, keelboat):
    """One dead morning should not erase a glorious afternoon."""
    day = build(fetcher).report(spot, keelboat, days=1, now=FIXTURE_NOW).days[0]
    ranked = sorted((h.value for h in day.daylight_hours), reverse=True)
    assert day.score == pytest.approx(sum(ranked[:3]) / 3)


def test_windows_respect_the_threshold(fetcher, spot, keelboat):
    report = build(fetcher).report(spot, keelboat, days=1, min_score=9.9, now=FIXTURE_NOW)
    assert report.days[0].windows == () or all(w.mean_score >= 9.9 for w in report.days[0].windows)


def test_observation_is_attached_when_the_spot_has_a_buoy(fetcher, spot, keelboat):
    report = build(fetcher).report(spot, keelboat, days=1, now=FIXTURE_NOW)
    assert report.observation is not None
    assert report.observation.station == "CHII2"


def test_live_can_be_switched_off(fetcher, spot, keelboat):
    report = build(fetcher).report(spot, keelboat, days=1, live=False, now=FIXTURE_NOW)
    assert report.observation is None
    assert not any("ndbc" in call for call in fetcher.calls)


def test_offline_buoy_is_a_note_not_a_failure(fetcher, spot, keelboat):
    fetcher.fail_on("ndbc", RuntimeError("station offline"))
    report = build(fetcher).report(spot, keelboat, days=1, now=FIXTURE_NOW)
    assert report.observation is None
    assert any("not reporting" in note for note in report.notes)


def test_divergence_between_buoy_and_model_is_called_out(fetcher, spot, keelboat):
    """The buoy in the fixture blows far harder than the grid forecast."""
    windy = FixtureFetcher(routes={**fetcher.routes, "ndbc.noaa.gov": "ndbc_gale.txt"})
    report = build(windy).report(spot, keelboat, days=1, now=FIXTURE_NOW)
    assert any("trust the water" in note for note in report.notes)


def test_missing_wave_grid_is_disclosed(fetcher, spot, keelboat):
    inland = FixtureFetcher(routes={**fetcher.routes, "/gridpoints/": "grid_inland.json"})
    report = build(inland).report(spot, keelboat, days=1, now=FIXTURE_NOW)
    assert any("No wave grid" in note for note in report.notes)
    assert all(hour.hour.wave_ft is None for day in report.days for hour in day.hours)


def test_hazards_flow_into_the_report_and_the_scores(spot, keelboat):
    stormy = FixtureFetcher(alerts="alerts_marine.json")
    report = build(stormy).report(spot, keelboat, days=1, now=FIXTURE_NOW)
    assert [h.event for h in report.hazards] == ["Small Craft Advisory", "Special Marine Warning"]
    warned = [
        hour
        for day in report.days
        for hour in day.hours
        if dt.time(14) <= hour.time.time() < dt.time(16)
    ]
    assert warned and all(hour.score.vetoed for hour in warned)


def test_one_broken_spot_does_not_sink_the_others(fetcher, spot, keelboat):
    broken = replace(spot, key="broken", name="Broken", lat=0.0, lon=0.0)
    fetcher.fail_on("/points/0.0000", RuntimeError("no grid here"))
    reports = build(fetcher).reports([broken, spot], keelboat, days=1, now=FIXTURE_NOW)
    assert len(reports) == 2
    assert reports[0].days == () and "unavailable" in reports[0].notes[0]
    assert reports[1].days, "the healthy spot still produced a forecast"


def test_headline_reads_like_a_sentence(fetcher, spot, keelboat):
    report = build(fetcher).report(spot, keelboat, days=1, now=FIXTURE_NOW)
    headline = report.headline()
    assert report.spot.name in headline
    assert "/10" in headline
