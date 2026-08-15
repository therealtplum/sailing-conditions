"""Configuration loading: TOML for preferences, environment for secrets."""

from __future__ import annotations

from pathlib import Path

import pytest

from sailing_conditions.settings import ConfigError, Settings

CONFIG = """
[defaults]
profile = "dinghy"
spots = ["sfbay", "chicago"]
min_score = 7.5
days = 4

[spots.home]
name = "The Dock"
region = "Somewhere, WI"
lat = 43.05
lon = -87.88
buoy = "45013"

[profiles.my_boat]
extends = "dinghy"
name = "My Laser"
wave_max_ft = 3.0

[[watch]]
spot = "home"
min_score = 8.0
channels = ["slack", "email"]
"""


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(CONFIG)
    return path


def test_defaults_without_a_config_file(tmp_path: Path):
    settings = Settings.load(env={}, config_path=tmp_path / "absent.toml")
    assert settings.profile == "keelboat"
    assert settings.spots == ("chicago",)
    assert settings.config_path is None


def test_preferences_come_from_the_file(config_file: Path):
    settings = Settings.load(env={}, config_path=config_file)
    assert settings.profile == "dinghy"
    assert settings.spots == ("sfbay", "chicago")
    assert settings.min_score == 7.5
    assert settings.days == 4
    assert settings.config_path == config_file


def test_user_spots_and_profiles_are_parsed(config_file: Path):
    settings = Settings.load(env={}, config_path=config_file)
    assert settings.user_spots["home"].name == "The Dock"
    assert settings.user_spots["home"].buoy == "45013"
    assert settings.user_profiles["my_boat"].wave_max_ft == 3.0
    assert settings.user_profiles["my_boat"].wind.ideal_hi == 16  # inherited from dinghy


def test_watch_rules_are_carried_through(config_file: Path):
    settings = Settings.load(env={}, config_path=config_file)
    assert len(settings.watch_rules) == 1
    assert settings.watch_rules[0]["spot"] == "home"


def test_secrets_come_only_from_the_environment(config_file: Path):
    env = {
        "SLACK_WEBHOOK_URL": "https://hooks.example/abc",
        "SMTP_HOST": "smtp.example",
        "SMTP_PORT": "465",
        "EMAIL_FROM": "me@example.com",
        "EMAIL_TO": "a@example.com; b@example.com,c@example.com",
        "SAILING_CONTACT": "me@example.com",
    }
    settings = Settings.load(env=env, config_path=config_file)
    assert settings.slack_configured
    assert settings.email_configured
    assert settings.smtp_port == 465
    assert settings.email_to == ("a@example.com", "b@example.com", "c@example.com")
    assert "me@example.com" in settings.user_agent
    assert CONFIG.find("SLACK") == -1, "the sample config carries no secrets"


def test_slack_needs_a_channel_with_a_token():
    assert not Settings.load(env={"SLACK_BOT_TOKEN": "xoxb-1"}, config_path=Path("/nope")).slack_configured
    assert Settings.load(
        env={"SLACK_BOT_TOKEN": "xoxb-1", "SLACK_CHANNEL": "#sailing"}, config_path=Path("/nope")
    ).slack_configured


def test_email_needs_a_recipient():
    settings = Settings.load(env={"SMTP_HOST": "smtp.example", "EMAIL_FROM": "me@example"}, config_path=Path("/nope"))
    assert not settings.email_configured


def test_cache_can_be_disabled_by_environment(tmp_path: Path):
    assert Settings.load(env={"SAILING_NO_CACHE": "1"}, config_path=tmp_path / "x.toml").cache_dir is None
    custom = Settings.load(env={"SAILING_CACHE_DIR": str(tmp_path)}, config_path=tmp_path / "x.toml")
    assert custom.cache_dir == tmp_path


def test_invalid_port_falls_back(tmp_path: Path):
    settings = Settings.load(env={"SMTP_PORT": "not-a-port"}, config_path=tmp_path / "x.toml")
    assert settings.smtp_port == 587


def test_malformed_config_is_loud(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text("[defaults\nprofile = ")
    with pytest.raises(ConfigError):
        Settings.load(env={}, config_path=path)


def test_invalid_user_spot_is_loud(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('[spots.broken]\nname = "No coordinates"\n')
    with pytest.raises(ConfigError, match="lat and lon"):
        Settings.load(env={}, config_path=path)


def test_config_path_can_come_from_the_environment(config_file: Path):
    settings = Settings.load(env={"SAILING_CONFIG": str(config_file)})
    assert settings.profile == "dinghy"


def test_spots_accept_a_comma_string(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('[defaults]\nspots = "miami, sfbay"\n')
    assert Settings.load(env={}, config_path=path).spots == ("miami", "sfbay")
