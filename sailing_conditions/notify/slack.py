"""Slack delivery, via incoming webhook or bot token."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any, Protocol

import requests

from ..models import Report
from ..render import slack as render_slack
from ..settings import Settings
from . import NotifyError

log = logging.getLogger(__name__)

WEBHOOK_TIMEOUT = 10.0
CHAT_POST_MESSAGE = "https://slack.com/api/chat.postMessage"


class Poster(Protocol):
    """The slice of ``requests.post`` this module depends on."""

    def __call__(self, url: str, **kwargs: Any) -> requests.Response:
        """Perform an HTTP POST."""
        ...


class SlackNotifier:
    """Posts a Block Kit message to a webhook or a channel."""

    name = "slack"

    def __init__(
        self,
        *,
        webhook: str | None = None,
        token: str | None = None,
        channel: str | None = None,
        poster: Poster | Callable[..., requests.Response] = requests.post,
    ) -> None:
        if not webhook and not (token and channel):
            raise ValueError("SlackNotifier needs either a webhook or a token and channel")
        self.webhook = webhook
        self.token = token
        self.channel = channel
        self._post = poster

    @classmethod
    def from_settings(cls, settings: Settings, **kwargs: Any) -> SlackNotifier:
        """Build from environment-derived settings."""
        return cls(
            webhook=settings.slack_webhook,
            token=settings.slack_token,
            channel=settings.slack_channel,
            **kwargs,
        )

    def send(self, subject: str, reports: Sequence[Report]) -> None:
        """Post the reports to Slack.

        Raises:
            NotifyError: on a transport failure or a Slack API error.
        """
        reports = list(reports)
        if not reports:
            return
        if len(reports) == 1:
            blocks = render_slack.report_blocks(reports[0])
            text = render_slack.fallback_text(reports[0])
        else:
            blocks = render_slack.digest_blocks(reports)
            text = subject

        payload: dict[str, Any] = {"text": text, "blocks": blocks}
        try:
            if self.webhook:
                response = self._post(self.webhook, json=payload, timeout=WEBHOOK_TIMEOUT)
                if not response.ok:
                    raise NotifyError(f"Slack webhook returned {response.status_code}: {response.text[:200]}")
                return

            payload["channel"] = self.channel
            response = self._post(
                CHAT_POST_MESSAGE,
                json=payload,
                headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json; charset=utf-8"},
                timeout=WEBHOOK_TIMEOUT,
            )
            body = response.json()
            if not body.get("ok"):
                raise NotifyError(f"Slack API error: {body.get('error', 'unknown')}")
        except requests.RequestException as exc:
            raise NotifyError(f"Slack request failed: {exc}") from exc
