"""Email delivery over SMTP.

Sends ``multipart/alternative`` with both a plain-text and an HTML part,
picks implicit TLS on port 465 and STARTTLS elsewhere, and takes its SMTP
class as an argument so the tests can assert on a real message object
without opening a socket.
"""

from __future__ import annotations

import smtplib
import ssl
from collections.abc import Callable, Sequence
from email.message import EmailMessage
from typing import Any

from ..models import Report
from ..render import html as render_html
from ..settings import Settings
from . import NotifyError

SMTP_TIMEOUT = 20.0
IMPLICIT_TLS_PORT = 465


class EmailNotifier:
    """Sends the HTML report to one or more recipients."""

    name = "email"

    def __init__(
        self,
        *,
        host: str,
        port: int = 587,
        sender: str,
        recipients: Sequence[str],
        user: str | None = None,
        password: str | None = None,
        smtp_factory: Callable[..., smtplib.SMTP] | None = None,
    ) -> None:
        if not host or not sender or not recipients:
            raise ValueError("EmailNotifier needs a host, a sender and at least one recipient")
        self.host = host
        self.port = port
        self.sender = sender
        self.recipients = list(recipients)
        self.user = user
        self.password = password
        self._smtp_factory = smtp_factory

    @classmethod
    def from_settings(cls, settings: Settings, **kwargs: Any) -> EmailNotifier:
        """Build from environment-derived settings."""
        return cls(
            host=settings.smtp_host or "",
            port=settings.smtp_port,
            sender=settings.email_from or "",
            recipients=settings.email_to,
            user=settings.smtp_user,
            password=settings.smtp_password,
            **kwargs,
        )

    def build_message(self, subject: str, reports: Sequence[Report]) -> EmailMessage:
        """Compose the multipart message without sending it."""
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.sender
        message["To"] = ", ".join(self.recipients)
        message.set_content(render_html.plain_text(list(reports)))
        message.add_alternative(render_html.build_email(list(reports), subject=subject), subtype="html")
        return message

    def send(self, subject: str, reports: Sequence[Report]) -> None:
        """Send the report by email.

        Raises:
            NotifyError: on any SMTP or socket failure.
        """
        reports = list(reports)
        if not reports:
            return
        message = self.build_message(subject, reports)
        try:
            with self._connect() as smtp:
                if self.user and self.password:
                    smtp.login(self.user, self.password)
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            raise NotifyError(f"SMTP send failed: {exc}") from exc

    def _connect(self) -> smtplib.SMTP:
        if self._smtp_factory is not None:
            return self._smtp_factory(self.host, self.port, timeout=SMTP_TIMEOUT)
        if self.port == IMPLICIT_TLS_PORT:
            return smtplib.SMTP_SSL(
                self.host, self.port, context=ssl.create_default_context(), timeout=SMTP_TIMEOUT
            )
        smtp = smtplib.SMTP(self.host, self.port, timeout=SMTP_TIMEOUT)
        smtp.ehlo()
        try:
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        except smtplib.SMTPNotSupportedError:
            pass  # plain relay on a trusted network
        return smtp
