"""Tests for senders module."""
from __future__ import annotations

import smtplib
from unittest.mock import Mock, patch

import pytest


class TestPostSlack:
    """Tests for post_slack function."""

    @patch("sailing_conditions.senders.requests.post")
    @patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"})
    def test_webhook_success(self, mock_post):
        """Test successful webhook post."""
        from sailing_conditions.senders import post_slack

        mock_post.return_value = Mock(status_code=200)
        post_slack("Test message")
        mock_post.assert_called_once()

    @patch("sailing_conditions.senders.requests.post")
    @patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"})
    def test_webhook_failure(self, mock_post, capsys):
        """Test webhook failure prints warning (doesn't raise on non-2xx)."""
        from sailing_conditions.senders import post_slack

        mock_post.return_value = Mock(status_code=500, text="Error")
        # Webhook failures on status code just print warning, don't raise
        post_slack("Test message")
        captured = capsys.readouterr()
        assert "webhook failed" in captured.err

    @patch("sailing_conditions.senders.requests.post")
    @patch.dict("os.environ", {"SLACK_BOT_TOKEN": "xoxb-test", "SLACK_CHANNEL": "C123"}, clear=True)
    def test_bot_token_success(self, mock_post):
        """Test successful bot token post."""
        from sailing_conditions.senders import post_slack

        mock_post.return_value = Mock()
        mock_post.return_value.json.return_value = {"ok": True}
        post_slack("Test message")
        mock_post.assert_called_once()

    @patch("sailing_conditions.senders.requests.post")
    @patch.dict("os.environ", {"SLACK_BOT_TOKEN": "xoxb-test", "SLACK_CHANNEL": "C123"}, clear=True)
    def test_bot_token_failure(self, mock_post, capsys):
        """Test bot token failure prints warning (doesn't raise on API error)."""
        from sailing_conditions.senders import post_slack

        mock_post.return_value = Mock()
        mock_post.return_value.json.return_value = {"ok": False, "error": "invalid_auth"}
        # Bot API failures just print warning, don't raise
        post_slack("Test message")
        captured = capsys.readouterr()
        assert "Slack API error" in captured.err

    @patch.dict("os.environ", {}, clear=True)
    def test_no_credentials(self, capsys):
        """Test with no Slack credentials."""
        from sailing_conditions.senders import post_slack

        post_slack("Test message")
        captured = capsys.readouterr()
        assert "No Slack credentials" in captured.out


class TestSendEmailHtml:
    """Tests for send_email_html function."""

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_env_vars(self, capsys):
        """Test with missing environment variables."""
        from sailing_conditions.senders import send_email_html

        send_email_html("Subject", "<html>Body</html>")
        captured = capsys.readouterr()
        assert "Email env vars not fully set" in captured.out

    @patch.dict(
        "os.environ",
        {
            "SMTP_HOST": "smtp.test.com",
            "SMTP_PORT": "invalid",
            "EMAIL_FROM": "from@test.com",
            "EMAIL_TO": "to@test.com",
        },
    )
    def test_invalid_port(self, capsys):
        """Test with invalid port."""
        from sailing_conditions.senders import send_email_html

        send_email_html("Subject", "<html>Body</html>")
        captured = capsys.readouterr()
        assert "Invalid SMTP_PORT" in captured.out

    @patch.dict(
        "os.environ",
        {
            "SMTP_HOST": "smtp.test.com",
            "SMTP_PORT": "587",
            "EMAIL_FROM": "from@test.com",
            "EMAIL_TO": "",
        },
    )
    def test_empty_recipients(self, capsys):
        """Test with empty recipients - caught by smtp_ready check."""
        from sailing_conditions.senders import send_email_html

        send_email_html("Subject", "<html>Body</html>")
        captured = capsys.readouterr()
        # Empty EMAIL_TO fails the _smtp_ready check first
        assert "Email env vars not fully set" in captured.out

    @patch("sailing_conditions.senders.smtplib.SMTP")
    @patch.dict(
        "os.environ",
        {
            "SMTP_HOST": "smtp.test.com",
            "SMTP_PORT": "587",
            "EMAIL_FROM": "from@test.com",
            "EMAIL_TO": "to@test.com",
        },
    )
    def test_successful_send_starttls(self, mock_smtp):
        """Test successful email send via STARTTLS."""
        from sailing_conditions.senders import send_email_html

        mock_instance = Mock()
        mock_smtp.return_value.__enter__ = Mock(return_value=mock_instance)
        mock_smtp.return_value.__exit__ = Mock(return_value=False)

        send_email_html("Subject", "<html>Body</html>", "Fallback text")

        mock_instance.ehlo.assert_called()
        mock_instance.sendmail.assert_called_once()

    @patch("sailing_conditions.senders.smtplib.SMTP_SSL")
    @patch.dict(
        "os.environ",
        {
            "SMTP_HOST": "smtp.test.com",
            "SMTP_PORT": "465",
            "EMAIL_FROM": "from@test.com",
            "EMAIL_TO": "to@test.com",
        },
    )
    def test_successful_send_ssl(self, mock_smtp_ssl):
        """Test successful email send via SSL."""
        from sailing_conditions.senders import send_email_html

        mock_instance = Mock()
        mock_smtp_ssl.return_value.__enter__ = Mock(return_value=mock_instance)
        mock_smtp_ssl.return_value.__exit__ = Mock(return_value=False)

        send_email_html("Subject", "<html>Body</html>")

        mock_instance.sendmail.assert_called_once()

    @patch("sailing_conditions.senders.smtplib.SMTP")
    @patch.dict(
        "os.environ",
        {
            "SMTP_HOST": "smtp.test.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "user",
            "SMTP_PASS": "pass",
            "EMAIL_FROM": "from@test.com",
            "EMAIL_TO": "to@test.com",
        },
    )
    def test_with_authentication(self, mock_smtp):
        """Test email send with authentication."""
        from sailing_conditions.senders import send_email_html

        mock_instance = Mock()
        mock_smtp.return_value.__enter__ = Mock(return_value=mock_instance)
        mock_smtp.return_value.__exit__ = Mock(return_value=False)

        send_email_html("Subject", "<html>Body</html>")

        mock_instance.login.assert_called_once_with("user", "pass")


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_split_addrs_comma(self):
        """Test splitting addresses by comma."""
        from sailing_conditions.senders import _split_addrs

        result = _split_addrs("a@test.com, b@test.com, c@test.com")
        assert result == ["a@test.com", "b@test.com", "c@test.com"]

    def test_split_addrs_semicolon(self):
        """Test splitting addresses by semicolon."""
        from sailing_conditions.senders import _split_addrs

        result = _split_addrs("a@test.com; b@test.com")
        assert result == ["a@test.com", "b@test.com"]

    def test_split_addrs_empty(self):
        """Test splitting empty string."""
        from sailing_conditions.senders import _split_addrs

        assert _split_addrs("") == []
        assert _split_addrs(None) == []

    def test_smtp_ready_missing_host(self):
        """Test SMTP ready check with missing host."""
        from sailing_conditions.senders import _smtp_ready

        params = {"host": None, "port": "587", "from": "a@test.com", "to": "b@test.com"}
        assert not _smtp_ready(params)

    def test_smtp_ready_all_present(self):
        """Test SMTP ready check with all required fields."""
        from sailing_conditions.senders import _smtp_ready

        params = {"host": "smtp.test.com", "port": "587", "from": "a@test.com", "to": "b@test.com"}
        assert _smtp_ready(params)

