"""Watch rules: matching, cooldown, delivery and error reporting."""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
from pathlib import Path

import pytest

from sailing_conditions.notify import NotifyError
from sailing_conditions.service import Forecaster
from sailing_conditions.settings import Settings
from sailing_conditions.sources.ndbc import NdbcClient
from sailing_conditions.sources.nws import NwsClient
from sailing_conditions.spots import SpotRegistry
from sailing_conditions.watch import WatchRule, WatchState, evaluate, run_watch
from tests.conftest import FIXTURE_NOW


class RecordingNotifier:
    name = "recording"

    def __init__(self, error: Exception | None = None):
        self.sent: list[tuple[str, int]] = []
        self.error = error

    def send(self, subject, reports):
        if self.error:
            raise self.error
        self.sent.append((subject, len(list(reports))))


@pytest.fixture
def registry(spot) -> SpotRegistry:
    return SpotRegistry({spot.key: spot})


@pytest.fixture
def forecaster(fetcher) -> Forecaster:
    return Forecaster(nws=NwsClient(fetcher), ndbc=NdbcClient(fetcher))


@pytest.fixture
def state(tmp_path: Path) -> WatchState:
    return WatchState.load(tmp_path / "state.json")


def test_rule_from_config():
    rule = WatchRule.from_mapping(
        {"spot": "chicago", "min_score": 8, "channels": "slack, email", "name": "weekend"}
    )
    assert rule.spot == "chicago"
    assert rule.min_score == 8.0
    assert rule.channels == ("slack", "email")
    assert rule.key == "weekend"


def test_rule_requires_a_spot():
    with pytest.raises(ValueError, match="spot"):
        WatchRule.from_mapping({"min_score": 8})


def test_rule_key_is_descriptive_without_a_name():
    assert WatchRule(spot="sfbay", profile="dinghy", min_score=7.5).key == "sfbay@dinghy>=7.5"


def test_evaluate_matches_the_first_qualifying_day(forecaster, spot, keelboat):
    report = forecaster.report(spot, keelboat, days=3, min_score=5.0, now=FIXTURE_NOW)
    hit = evaluate(WatchRule(spot="chicago", min_score=5.0, min_hours=2), report)
    assert hit is not None
    assert hit.day is report.days[0] or hit.day in report.days
    assert hit.window.mean_score >= 5.0
    assert "/10" in hit.headline()


def test_evaluate_returns_nothing_when_the_bar_is_too_high(forecaster, spot, keelboat):
    report = forecaster.report(spot, keelboat, days=3, min_score=9.99, now=FIXTURE_NOW)
    assert evaluate(WatchRule(spot="chicago", min_score=9.99), report) is None


def test_run_watch_notifies_on_a_match(forecaster, registry, settings, state):
    notifier = RecordingNotifier()
    rule = WatchRule(spot="chicago", min_score=4.0, min_hours=2)
    hits, errors = run_watch(
        [rule],
        forecaster=forecaster,
        registry=registry,
        settings=settings,
        state=state,
        notifiers={rule.key: [notifier]},
        now=FIXTURE_NOW,
    )
    assert len(hits) == 1
    assert errors == []
    assert len(notifier.sent) == 1
    assert state.path.exists(), "state is persisted so the next run can dedupe"


def test_cooldown_suppresses_a_repeat_run(forecaster, registry, settings, state):
    notifier = RecordingNotifier()
    rule = WatchRule(spot="chicago", min_score=4.0, cooldown_hours=20)
    kwargs = dict(
        forecaster=forecaster,
        registry=registry,
        settings=settings,
        state=state,
        notifiers={rule.key: [notifier]},
    )
    run_watch([rule], now=FIXTURE_NOW, **kwargs)
    hits, _ = run_watch([rule], now=FIXTURE_NOW + dt.timedelta(hours=2), **kwargs)
    assert hits == []
    assert len(notifier.sent) == 1


def test_cooldown_expires(forecaster, registry, settings, state):
    notifier = RecordingNotifier()
    rule = WatchRule(spot="chicago", min_score=4.0, cooldown_hours=1)
    kwargs = dict(
        forecaster=forecaster,
        registry=registry,
        settings=settings,
        state=state,
        notifiers={rule.key: [notifier]},
    )
    run_watch([rule], now=FIXTURE_NOW, **kwargs)
    hits, _ = run_watch([rule], now=FIXTURE_NOW + dt.timedelta(hours=3), **kwargs)
    assert len(hits) == 1
    assert len(notifier.sent) == 2


def test_dry_run_neither_sends_nor_persists(forecaster, registry, settings, state):
    notifier = RecordingNotifier()
    rule = WatchRule(spot="chicago", min_score=4.0)
    hits, errors = run_watch(
        [rule],
        forecaster=forecaster,
        registry=registry,
        settings=settings,
        state=state,
        notifiers={rule.key: [notifier]},
        now=FIXTURE_NOW,
        dry_run=True,
    )
    assert len(hits) == 1
    assert errors == []
    assert notifier.sent == []
    assert not state.path.exists()


def test_a_failed_delivery_is_reported_and_not_recorded(forecaster, registry, settings, state):
    """A dropped message must be retried next run, not silently forgotten."""
    rule = WatchRule(spot="chicago", min_score=4.0)
    hits, errors = run_watch(
        [rule],
        forecaster=forecaster,
        registry=registry,
        settings=settings,
        state=state,
        notifiers={rule.key: [RecordingNotifier(error=NotifyError("slack down"))]},
        now=FIXTURE_NOW,
    )
    assert len(hits) == 1
    assert any("slack down" in error for error in errors)
    assert state.fired == {}


def test_unknown_spot_is_an_error_not_a_crash(forecaster, registry, settings, state):
    hits, errors = run_watch(
        [WatchRule(spot="atlantis")],
        forecaster=forecaster,
        registry=registry,
        settings=settings,
        state=state,
        now=FIXTURE_NOW,
    )
    assert hits == []
    assert any("atlantis" in error for error in errors)


def test_missing_channel_is_reported(forecaster, registry, settings, state):
    hits, errors = run_watch(
        [WatchRule(spot="chicago", min_score=4.0, channels=("slack",))],
        forecaster=forecaster,
        registry=registry,
        settings=settings,  # no Slack credentials
        state=state,
        now=FIXTURE_NOW,
    )
    assert len(hits) == 1
    assert any("no configured channel" in error for error in errors)


def test_state_survives_a_round_trip(tmp_path: Path):
    rule = WatchRule(spot="chicago")
    state = WatchState.load(tmp_path / "state.json")
    state.record(rule, dt.date(2026, 8, 15), FIXTURE_NOW)
    state.save()

    reloaded = WatchState.load(tmp_path / "state.json")
    assert reloaded.suppressed(rule, dt.date(2026, 8, 15), FIXTURE_NOW)
    assert not reloaded.suppressed(rule, dt.date(2026, 8, 16), FIXTURE_NOW)


def test_state_tolerates_a_corrupt_file(tmp_path: Path):
    path = tmp_path / "state.json"
    path.write_text("{{{")
    assert WatchState.load(path).fired == {}


def test_state_prunes_old_entries(tmp_path: Path):
    rule = WatchRule(spot="chicago")
    state = WatchState.load(tmp_path / "state.json")
    state.record(rule, dt.date(2026, 8, 1), FIXTURE_NOW)
    state.record(rule, dt.date(2026, 8, 20), FIXTURE_NOW)
    state.prune(dt.date(2026, 8, 15))
    assert len(state.fired) == 1


def test_rules_from_settings(tmp_path: Path):
    from sailing_conditions.watch import rules_from_settings

    settings = Settings(watch_rules=({"spot": "chicago", "min_score": 9},))
    assert rules_from_settings(settings)[0].min_score == 9.0


def test_rule_profile_reaches_the_scorer(forecaster, registry, settings, state):
    """The rule's profile must be the one the report is scored against."""
    kwargs = dict(forecaster=forecaster, registry=registry, settings=settings, state=state, dry_run=True)
    beginner = WatchRule(spot="chicago", profile="beginner", min_score=1.0, name="b")
    heavy = replace(beginner, profile="heavy_air", name="h")

    hit_beginner = run_watch([beginner], now=FIXTURE_NOW, **kwargs)[0][0]
    hit_heavy = run_watch([heavy], now=FIXTURE_NOW, **kwargs)[0][0]

    assert hit_beginner.report.profile_key == "beginner"
    assert hit_heavy.report.profile_key == "heavy_air"
    assert hit_beginner.day.score != hit_heavy.day.score, "profiles must change the numbers"
