"""Renderers: console, JSON, Slack blocks, HTML email."""

from __future__ import annotations

import json

import pytest
from rich.console import Console

from sailing_conditions.models import Hazard, Report, Spot
from sailing_conditions.render import html as render_html
from sailing_conditions.render import jsonout
from sailing_conditions.render import slack as render_slack
from sailing_conditions.render.console import render_report, render_summary
from sailing_conditions.service import Forecaster
from sailing_conditions.sources.ndbc import NdbcClient
from sailing_conditions.sources.nws import NwsClient
from tests.conftest import FIXTURE_NOW, FixtureFetcher


@pytest.fixture
def report(fetcher, spot, keelboat) -> Report:
    forecaster = Forecaster(nws=NwsClient(fetcher), ndbc=NdbcClient(fetcher))
    return forecaster.report(spot, keelboat, days=2, now=FIXTURE_NOW)


def capture(renderer, *args) -> str:
    console = Console(record=True, width=100, no_color=True, legacy_windows=False)
    renderer(*args, console) if len(args) else renderer(console)
    return console.export_text()


def test_console_report_leads_with_the_decision(report):
    console = Console(record=True, width=100, no_color=True)
    render_report(report, console)
    text = console.export_text()
    assert "Belmont Harbor" in text
    assert "Today" in text
    assert "/10" in text
    assert "go" in text
    assert "buoy CHII2" in text


def test_console_explain_shows_the_arithmetic(report):
    console = Console(record=True, width=110, no_color=True)
    render_report(report, console, explain=True)
    text = console.export_text()
    assert "why" in text
    assert "wind" in text and "weight" in text


def test_console_summary_ranks_spots(report):
    console = Console(record=True, width=110, no_color=True)
    render_summary([report], console)
    text = console.export_text()
    assert "Sailing outlook" in text
    assert "Belmont Harbor" in text


def test_console_handles_an_empty_report():
    empty = Report(
        spot=Spot(key="x", name="Nowhere", lat=0, lon=0),
        profile_key="keelboat",
        generated_at=FIXTURE_NOW,
        timezone="UTC",
        notes=("Forecast unavailable: grid down",),
    )
    console = Console(record=True, width=100, no_color=True)
    render_report(empty, console)
    render_summary([empty], console)
    text = console.export_text()
    assert "no forecast days available" in text
    assert "grid down" in text


def test_json_round_trips_and_declares_a_schema(report):
    payload = json.loads(jsonout.dumps([report]))
    assert payload["schema_version"] == jsonout.SCHEMA_VERSION
    assert payload["count"] == 1

    first = payload["reports"][0]
    assert first["spot"]["key"] == "chicago"
    assert first["profile"] == "keelboat"
    assert first["headline"]
    assert len(first["days"]) == 2

    day = first["days"][0]
    assert day["score"] == pytest.approx(report.days[0].score, abs=0.01)
    assert day["hours"], "hourly detail included by default"
    assert day["hours"][0]["score"]["factors"], "factors are part of the contract"


def test_json_compact_mode_drops_the_hours(report):
    payload = json.loads(jsonout.dumps([report], hourly=False))
    assert "hours" not in payload["reports"][0]["days"][0]


def test_json_is_serialisable_with_hazards_and_observations(spot, keelboat):
    stormy = FixtureFetcher(alerts="alerts_marine.json")
    report = Forecaster(nws=NwsClient(stormy), ndbc=NdbcClient(stormy)).report(
        spot, keelboat, days=1, now=FIXTURE_NOW
    )
    payload = json.loads(jsonout.dumps([report]))["reports"][0]
    assert payload["hazards"][0]["event"] == "Small Craft Advisory"
    assert payload["observation"]["station"] == "CHII2"


def test_slack_blocks_are_well_formed(report):
    blocks = render_slack.report_blocks(report)
    assert blocks[0]["type"] == "header"
    assert all("type" in block for block in blocks)
    rendered = json.dumps(blocks)
    assert "Belmont Harbor" in rendered
    assert len(rendered) < 4000, "Slack rejects oversized payloads"
    assert render_slack.fallback_text(report) == report.headline()


def test_slack_digest_ranks_by_score(report):
    blocks = render_slack.digest_blocks([report, report])
    assert blocks[0]["type"] == "header"
    assert len(blocks) == 3


def test_html_email_contains_the_essentials(report):
    body = render_html.build_email([report])
    assert body.startswith("<!doctype html>")
    assert "Belmont Harbor" in body
    assert "Today" in body
    assert "NOAA" in body, "attribution and a safety note belong in the footer"


def test_html_escapes_forecast_text():
    """Forecast text is third-party input; it must not become markup."""
    spot = Spot(key="x", name="<script>alert(1)</script>", lat=0, lon=0)
    report = Report(
        spot=spot,
        profile_key="keelboat",
        generated_at=FIXTURE_NOW,
        timezone="UTC",
        hazards=(Hazard(event="X", severity="Severe", headline="<img src=x onerror=1>"),),
    )
    body = render_html.build_email([report])
    assert "<script>" not in body
    assert "&lt;script&gt;" in body
    assert "<img src=x" not in body


def test_plain_text_alternative(report):
    text = render_html.plain_text([report])
    assert report.spot.name in text
    assert "/10" in text
