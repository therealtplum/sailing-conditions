"""Delivery channels, exercised with fake transports."""

from __future__ import annotations

import json
from typing import ClassVar

import pytest
import requests

from sailing_conditions.models import Report, Spot
from sailing_conditions.notify import NotifyError, build_notifiers
from sailing_conditions.notify.email import EmailNotifier
from sailing_conditions.notify.slack import SlackNotifier
from sailing_conditions.settings import Settings
from tests.conftest import FIXTURE_NOW


@pytest.fixture
def report() -> Report:
    return Report(
        spot=Spot(key="chicago", name="Belmont Harbor", lat=41.9, lon=-87.6, region="Chicago, IL"),
        profile_key="keelboat",
        generated_at=FIXTURE_NOW,
        timezone="America/Chicago",
    )


class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self.text = json.dumps(body or {"ok": True})
        self._body = body or {"ok": True}

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._body


class FakePoster:
    def __init__(self, response=None, error: Exception | None = None):
        self.response = response or FakeResponse()
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response


def test_slack_webhook_posts_blocks_and_fallback_text(report):
    poster = FakePoster()
    SlackNotifier(webhook="https://hooks.example/abc", poster=poster).send("subject", [report])
    url, kwargs = poster.calls[0]
    assert url == "https://hooks.example/abc"
    assert kwargs["json"]["text"] == report.headline()
    assert kwargs["json"]["blocks"][0]["type"] == "header"


def test_slack_bot_token_targets_a_channel(report):
    poster = FakePoster()
    SlackNotifier(token="xoxb-1", channel="#sailing", poster=poster).send("subject", [report])
    url, kwargs = poster.calls[0]
    assert url.endswith("chat.postMessage")
    assert kwargs["json"]["channel"] == "#sailing"
    assert kwargs["headers"]["Authorization"] == "Bearer xoxb-1"


def test_slack_uses_a_digest_for_several_reports(report):
    poster = FakePoster()
    SlackNotifier(webhook="https://hooks.example/abc", poster=poster).send("digest", [report, report])
    assert poster.calls[0][1]["json"]["text"] == "digest"


def test_slack_reports_an_http_failure(report):
    poster = FakePoster(FakeResponse(status=500, body={"error": "boom"}))
    with pytest.raises(NotifyError, match="500"):
        SlackNotifier(webhook="https://hooks.example/abc", poster=poster).send("subject", [report])


def test_slack_reports_an_api_error(report):
    poster = FakePoster(FakeResponse(body={"ok": False, "error": "channel_not_found"}))
    with pytest.raises(NotifyError, match="channel_not_found"):
        SlackNotifier(token="xoxb-1", channel="#nope", poster=poster).send("subject", [report])


def test_slack_reports_a_transport_failure(report):
    poster = FakePoster(error=requests.ConnectionError("no route"))
    with pytest.raises(NotifyError, match="no route"):
        SlackNotifier(webhook="https://hooks.example/abc", poster=poster).send("subject", [report])


def test_slack_needs_a_destination():
    with pytest.raises(ValueError):
        SlackNotifier()


def test_slack_ignores_an_empty_report_list():
    poster = FakePoster()
    SlackNotifier(webhook="https://hooks.example/abc", poster=poster).send("subject", [])
    assert poster.calls == []


class FakeSMTP:
    instances: ClassVar[list[FakeSMTP]] = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.logins: list[tuple[str, str]] = []
        self.messages: list = []
        self.closed = False
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True

    def login(self, user, password):
        self.logins.append((user, password))

    def send_message(self, message):
        self.messages.append(message)


def test_email_builds_a_multipart_message(report):
    notifier = EmailNotifier(
        host="smtp.example", sender="me@example.com", recipients=["you@example.com"], smtp_factory=FakeSMTP
    )
    message = notifier.build_message("Sailing", [report])
    assert message["Subject"] == "Sailing"
    assert message["To"] == "you@example.com"
    assert message.is_multipart()
    types = {part.get_content_type() for part in message.walk()}
    assert {"text/plain", "text/html"} <= types


def test_email_sends_and_authenticates(report):
    FakeSMTP.instances.clear()
    EmailNotifier(
        host="smtp.example",
        port=587,
        sender="me@example.com",
        recipients=["you@example.com"],
        user="me",
        password="secret",
        smtp_factory=FakeSMTP,
    ).send("Sailing", [report])
    smtp = FakeSMTP.instances[-1]
    assert smtp.logins == [("me", "secret")]
    assert len(smtp.messages) == 1
    assert smtp.closed


def test_email_skips_login_without_credentials(report):
    FakeSMTP.instances.clear()
    EmailNotifier(
        host="smtp.example", sender="me@example.com", recipients=["you@example.com"], smtp_factory=FakeSMTP
    ).send("Sailing", [report])
    assert FakeSMTP.instances[-1].logins == []


def test_email_wraps_transport_errors(report):
    def exploding(*args, **kwargs):
        raise OSError("connection refused")

    notifier = EmailNotifier(
        host="smtp.example", sender="me@example.com", recipients=["you@example.com"], smtp_factory=exploding
    )
    with pytest.raises(NotifyError, match="connection refused"):
        notifier.send("Sailing", [report])


def test_email_requires_a_recipient():
    with pytest.raises(ValueError):
        EmailNotifier(host="smtp.example", sender="me@example.com", recipients=[])


def test_build_notifiers_skips_unconfigured_channels():
    settings = Settings()
    assert build_notifiers(settings, ["slack", "email"]) == []

    configured = Settings(
        slack_webhook="https://hooks.example/abc",
        smtp_host="smtp.example",
        email_from="me@example.com",
        email_to=("you@example.com",),
    )
    names = {n.name for n in build_notifiers(configured, ["slack", "email"])}
    assert names == {"slack", "email"}
    assert {n.name for n in build_notifiers(configured, ["slack"])} == {"slack"}
