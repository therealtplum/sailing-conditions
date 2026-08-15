"""Configuration: a TOML file for preferences, environment for secrets.

The split is deliberate. Your home spot, your boat and your thresholds are
things you want in version control or a dotfiles repo; your Slack webhook
and SMTP password are not. Preferences live in

``~/.config/sailing-conditions/config.toml`` (override with ``SAILING_CONFIG``)

and every credential is read from the environment, so nothing secret is
ever written to disk by this tool.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import Spot
from .profiles import DEFAULT_PROFILE, BoatProfile, profile_from_mapping
from .spots import load_spot_table

CONFIG_ENV = "SAILING_CONFIG"
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "sailing-conditions" / "config.toml"
DEFAULT_CACHE_DIR = Path(
    os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
) / "sailing-conditions"
DEFAULT_STATE_PATH = Path(
    os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))
) / "sailing-conditions" / "watch-state.json"

DEFAULT_SPOTS = ("chicago",)
DEFAULT_MIN_SCORE = 6.0
DEFAULT_DAYS = 2

PACKAGE_VERSION = "2.0.0"


class ConfigError(RuntimeError):
    """The config file exists but could not be used."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything the CLI needs that is not a command-line flag."""

    contact: str = "anonymous@example.com"
    """Contact address sent in the NWS User-Agent, as their API asks."""

    profile: str = DEFAULT_PROFILE
    spots: tuple[str, ...] = DEFAULT_SPOTS
    min_score: float = DEFAULT_MIN_SCORE
    min_hours: int = 2
    days: int = DEFAULT_DAYS

    cache_dir: Path | None = DEFAULT_CACHE_DIR
    state_path: Path = DEFAULT_STATE_PATH

    slack_webhook: str | None = None
    slack_token: str | None = None
    slack_channel: str | None = None

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    email_from: str | None = None
    email_to: tuple[str, ...] = ()

    user_spots: Mapping[str, Spot] = field(default_factory=dict)
    user_profiles: Mapping[str, BoatProfile] = field(default_factory=dict)
    watch_rules: tuple[Mapping[str, Any], ...] = ()
    config_path: Path | None = None

    @property
    def user_agent(self) -> str:
        """NWS asks for an identifying UA with a contact address."""
        return f"sailing-conditions/{PACKAGE_VERSION} ({self.contact})"

    @property
    def slack_configured(self) -> bool:
        """Whether a Slack destination is available."""
        return bool(self.slack_webhook or (self.slack_token and self.slack_channel))

    @property
    def email_configured(self) -> bool:
        """Whether SMTP is configured well enough to attempt a send."""
        return bool(self.smtp_host and self.email_from and self.email_to)

    @classmethod
    def load(
        cls,
        *,
        env: Mapping[str, str] | None = None,
        config_path: Path | str | None = None,
    ) -> Settings:
        """Build settings from a config file plus environment overrides.

        A missing config file is normal and produces defaults. A *malformed*
        one raises :class:`ConfigError`, because silently ignoring the file
        you just edited is maddening.
        """
        env = os.environ if env is None else env
        path = _resolve_config_path(env, config_path)
        raw = _read_config(path)

        defaults = raw.get("defaults", {}) if isinstance(raw.get("defaults"), Mapping) else {}
        try:
            user_spots = load_spot_table(raw.get("spots", {}) or {})
        except ValueError as exc:
            raise ConfigError(f"{path}: {exc}") from exc
        user_profiles = {
            key: profile_from_mapping(key, value)
            for key, value in (raw.get("profiles", {}) or {}).items()
        }

        cache_dir: Path | None = Path(env["SAILING_CACHE_DIR"]) if env.get("SAILING_CACHE_DIR") else DEFAULT_CACHE_DIR
        if _truthy(env.get("SAILING_NO_CACHE")):
            cache_dir = None

        return cls(
            contact=env.get("SAILING_CONTACT") or str(defaults.get("contact", "anonymous@example.com")),
            profile=str(defaults.get("profile", DEFAULT_PROFILE)),
            spots=_as_tuple(defaults.get("spots"), DEFAULT_SPOTS),
            min_score=float(defaults.get("min_score", DEFAULT_MIN_SCORE)),
            min_hours=int(defaults.get("min_hours", 2)),
            days=int(defaults.get("days", DEFAULT_DAYS)),
            cache_dir=cache_dir,
            state_path=Path(env.get("SAILING_STATE_FILE") or str(defaults.get("state_file", DEFAULT_STATE_PATH))),
            slack_webhook=env.get("SLACK_WEBHOOK_URL") or None,
            slack_token=env.get("SLACK_BOT_TOKEN") or None,
            slack_channel=env.get("SLACK_CHANNEL") or None,
            smtp_host=env.get("SMTP_HOST") or None,
            smtp_port=_as_int(env.get("SMTP_PORT"), 587),
            smtp_user=env.get("SMTP_USER") or None,
            smtp_password=env.get("SMTP_PASS") or None,
            email_from=env.get("EMAIL_FROM") or None,
            email_to=_split_addresses(env.get("EMAIL_TO")),
            user_spots=user_spots,
            user_profiles=user_profiles,
            watch_rules=tuple(raw.get("watch", ()) or ()),
            config_path=path if path and path.exists() else None,
        )


def _resolve_config_path(env: Mapping[str, str], override: Path | str | None) -> Path:
    if override is not None:
        return Path(override).expanduser()
    if env.get(CONFIG_ENV):
        return Path(env[CONFIG_ENV]).expanduser()
    return DEFAULT_CONFIG_PATH


def _read_config(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text("utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"could not read {path}: {exc}") from exc


def _as_tuple(value: Any, fallback: Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return tuple(str(item) for item in value)
    return tuple(fallback)


def _as_int(value: Any, fallback: int) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return fallback


def _truthy(value: str | None) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _split_addresses(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in value.replace(";", ",").split(",") if part.strip())
