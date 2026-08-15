"""Delivery channels.

A notifier takes finished reports and puts them in front of a human. Both
implementations take their transport as a constructor argument, so the
tests exercise the real message-building code with no network and no
mocking framework.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol, runtime_checkable

from ..models import Report
from ..settings import Settings


class NotifyError(RuntimeError):
    """A channel was configured but the send failed."""


@runtime_checkable
class Notifier(Protocol):
    """Anything that can deliver a set of reports."""

    name: str

    def send(self, subject: str, reports: Sequence[Report]) -> None:
        """Deliver the reports, raising :class:`NotifyError` on failure."""
        ...


def build_notifiers(settings: Settings, channels: Iterable[str]) -> list[Notifier]:
    """Instantiate the requested channels that are actually configured.

    Unconfigured channels are skipped silently: asking for Slack on a box
    with no webhook should not crash a cron job that also sends email.
    """
    from .email import EmailNotifier
    from .slack import SlackNotifier

    built: list[Notifier] = []
    wanted = {channel.strip().lower() for channel in channels}
    if "slack" in wanted and settings.slack_configured:
        built.append(SlackNotifier.from_settings(settings))
    if "email" in wanted and settings.email_configured:
        built.append(EmailNotifier.from_settings(settings))
    return built


__all__ = ["Notifier", "NotifyError", "build_notifiers"]
