"""End-to-end CLI tests.

These run the real ``main()`` — argument parsing, settings, service wiring,
rendering — with only the HTTP layer swapped for recorded fixtures.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rich.console import Console

from sailing_conditions.cli import EXIT_ERROR, EXIT_OK, EXIT_USAGE, main
from sailing_conditions.settings import Settings
from tests.conftest import FixtureFetcher


@pytest.fixture
def console() -> Console:
    return Console(record=True, width=110, no_color=True, legacy_windows=False)


def run(argv, fetcher, console, settings) -> tuple[int, str]:
    code = main(argv, fetcher=fetcher, console=console, settings=settings)
    return code, console.export_text()


def test_now_renders_a_report(fetcher, console, settings):
    code, text = run(["now", "chicago"], fetcher, console, settings)
    assert code == EXIT_OK
    assert "Belmont Harbor" in text
    assert "/10" in text
    assert "buoy CHII2" in text


def test_now_falls_back_to_configured_spots(fetcher, console, settings):
    code, text = run(["now"], fetcher, console, settings)
    assert code == EXIT_OK
    assert "Belmont Harbor" in text


def test_plan_accepts_a_day_count(fetcher, console, settings):
    code, text = run(["plan", "chicago", "--days", "2"], fetcher, console, settings)
    assert code == EXIT_OK
    assert "Today" in text and "Tomorrow" in text


def test_day_count_is_clamped(fetcher, console, settings):
    code, _ = run(["plan", "chicago", "--days", "99"], fetcher, console, settings)
    assert code == EXIT_OK


def test_explain_prints_the_factor_table(fetcher, console, settings):
    code, text = run(["now", "chicago", "--explain"], fetcher, console, settings)
    assert code == EXIT_OK
    assert "why" in text
    assert "weight" in text


def test_profile_flag_changes_the_score(fetcher, settings):
    scores = {}
    for profile in ("beginner", "heavy_air"):
        console = Console(record=True, width=110, no_color=True)
        code = main(
            ["now", "chicago", "--profile", profile, "--json", "--compact"],
            fetcher=FixtureFetcher(),
            console=console,
            settings=settings,
        )
        assert code == EXIT_OK
        payload = json.loads(console.export_text())
        scores[profile] = payload["reports"][0]["days"][0]["score"]
    assert scores["beginner"] != scores["heavy_air"]


def test_json_output_is_machine_readable(fetcher, console, settings):
    code, text = run(["now", "chicago", "--json"], fetcher, console, settings)
    assert code == EXIT_OK
    payload = json.loads(text)
    assert payload["reports"][0]["spot"]["key"] == "chicago"
    assert payload["reports"][0]["days"][0]["hours"]


def test_compare_ranks_spots(fetcher, console, settings):
    code, text = run(["compare", "chicago", "chicago"], fetcher, console, settings)
    assert code == EXIT_OK
    assert "Sailing outlook" in text


def test_spots_lists_the_registry(fetcher, console, settings):
    code, text = run(["spots"], fetcher, console, settings)
    assert code == EXIT_OK
    assert "chicago" in text and "Belmont Harbor" in text
    assert "config.toml" in text


def test_spots_can_filter_by_tag(fetcher, console, settings):
    code, text = run(["spots", "--tag", "great-lakes"], fetcher, console, settings)
    assert code == EXIT_OK
    assert "Milwaukee" in text
    assert "Key West" not in text


def test_spots_json(fetcher, console, settings):
    code, text = run(["spots", "--json"], fetcher, console, settings)
    assert code == EXIT_OK
    assert any(entry["key"] == "chicago" for entry in json.loads(text))


def test_profiles_lists_wind_bands(fetcher, console, settings):
    code, text = run(["profiles"], fetcher, console, settings)
    assert code == EXIT_OK
    assert "keelboat" in text and "kt" in text


def test_user_spots_appear_in_the_registry(fetcher, console, tmp_path: Path):
    config = tmp_path / "config.toml"
    config.write_text('[spots.home]\nname = "My Dock"\nregion = "Chicago, IL"\nlat = 41.9\nlon = -87.6\n')
    settings = Settings.load(env={}, config_path=config)
    code, text = run(["spots"], fetcher, console, settings)
    assert code == EXIT_OK
    assert "My Dock" in text


def test_unknown_spot_exits_with_a_usage_code(fetcher, console, settings):
    code, text = run(["now", "chigago"], fetcher, console, settings)
    assert code == EXIT_USAGE
    assert "Did you mean: chicago" in text


def test_unknown_profile_exits_with_a_usage_code(fetcher, console, settings):
    code, text = run(["now", "chicago", "--profile", "dreadnought"], fetcher, console, settings)
    assert code == EXIT_USAGE
    assert "unknown profile" in text


def test_network_failure_is_reported_per_spot(console, settings):
    fetcher = FixtureFetcher()
    fetcher.fail_on("/points/", RuntimeError("api.weather.gov is down"))
    code, text = run(["now", "chicago"], fetcher, console, settings)
    assert code == EXIT_OK, "one dead spot is a note on the report, not a crash"
    assert "unavailable" in text


def test_no_arguments_prints_help(console, settings):
    code, _ = run([], FixtureFetcher(), console, settings)
    assert code == EXIT_USAGE


def test_version_flag():
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == EXIT_OK


def test_watch_without_rules_says_so(fetcher, console, settings):
    code, text = run(["watch"], fetcher, console, settings)
    assert code == EXIT_OK
    assert "No watch rules configured" in text


def test_watch_dry_run_evaluates_rules(fetcher, console, tmp_path: Path):
    settings = Settings(
        cache_dir=None,
        state_path=tmp_path / "state.json",
        watch_rules=({"spot": "chicago", "min_score": 4.0},),
    )
    code, text = run(["watch", "--dry-run"], fetcher, console, settings)
    assert code == EXIT_OK
    assert "would notify" in text or "nothing worth a message" in text
    assert not (tmp_path / "state.json").exists()


def test_watch_reports_a_broken_rule(fetcher, console, tmp_path: Path):
    settings = Settings(
        cache_dir=None,
        state_path=tmp_path / "state.json",
        watch_rules=({"spot": "atlantis", "min_score": 4.0},),
    )
    code, text = run(["watch", "--dry-run"], fetcher, console, settings)
    assert code == EXIT_ERROR
    assert "atlantis" in text
