"""Buoy observation parsing."""

from __future__ import annotations

import datetime as dt

import pytest

from sailing_conditions.sources.ndbc import NdbcClient, parse_realtime
from tests.conftest import FixtureFetcher, load_fixture


def test_parses_the_latest_row():
    observation = parse_realtime(load_fixture("ndbc_chii2.txt"), "chii2")
    assert observation is not None
    assert observation.station == "CHII2"
    assert observation.time == dt.datetime(2026, 8, 15, 9, 0, tzinfo=dt.UTC)
    assert observation.wind_kt == pytest.approx(7.0, abs=0.1)  # 3.6 m/s
    assert observation.gust_kt == pytest.approx(8.0, abs=0.1)
    assert observation.wind_dir == "S"
    assert observation.air_temp_f == pytest.approx(73.9, abs=0.3)  # 23.3 C


def test_missing_values_become_none():
    observation = parse_realtime(load_fixture("ndbc_chii2.txt"), "CHII2")
    assert observation.wave_ft is None, "this crib station reports no waves"
    assert observation.water_temp_f is None, "and no water temperature"


def test_gaps_are_filled_from_recent_rows():
    """Sensors report on different cadences; the newest row is often partial."""
    text = "\n".join(
        [
            "#YY  MM DD hh mm WDIR WSPD GST  WVHT  WTMP",
            "#yr  mo dy hr mn degT m/s  m/s     m  degC",
            "2026 08 15 09 00 190  4.1  5.1    MM    MM",
            "2026 08 15 08 50 190  4.0  5.0   0.6  22.0",
        ]
    )
    observation = parse_realtime(text, "TEST")
    assert observation.time.minute == 0, "timestamp comes from the newest row"
    assert observation.wave_ft == pytest.approx(2.0, abs=0.1), "wave height back-filled"
    assert observation.water_temp_f == pytest.approx(71.6, abs=0.2)


def test_lookback_is_bounded():
    rows = ["#YY  MM DD hh mm WVHT", "#yr  mo dy hr mn     m"]
    rows += [f"2026 08 15 09 {60 - minute:02d} MM" for minute in range(1, 20)]
    rows.append("2026 08 14 12 00 1.0")
    observation = parse_realtime("\n".join(rows), "TEST", lookback_rows=5)
    assert observation.wave_ft is None, "yesterday's reading is not 'current'"


def test_wave_only_station():
    observation = parse_realtime(load_fixture("ndbc_waves_only.txt"), "46221")
    assert observation.wind_kt is None
    assert observation.wave_ft == pytest.approx(3.3, abs=0.1)
    assert observation.wave_period_s == 18
    assert "3.3 ft" in observation.describe()


def test_describe_without_data():
    observation = parse_realtime(
        "#YY  MM DD hh mm WSPD\n#yr  mo dy hr mn m/s\n2026 08 15 09 00 MM", "TEST"
    )
    assert observation.describe() == "no data"


@pytest.mark.parametrize("text", ["", "#YY MM DD hh mm WSPD", "not a table at all"])
def test_unusable_input_returns_none(text):
    assert parse_realtime(text, "TEST") is None


def test_malformed_timestamp_returns_none():
    text = "#YY  MM DD hh mm WSPD\n#yr  mo dy hr mn m/s\n2026 13 45 99 99  4.0"
    assert parse_realtime(text, "TEST") is None


def test_client_fetches_and_parses(fetcher):
    observation = NdbcClient(fetcher).latest("chii2")
    assert observation is not None
    assert "ndbc.noaa.gov" in fetcher.calls[0]
    assert "CHII2" in fetcher.calls[0], "station IDs are upper-cased in the URL"


def test_client_returns_none_when_the_buoy_is_offline():
    fetcher = FixtureFetcher()
    fetcher.fail_on("ndbc", RuntimeError("404"))
    assert NdbcClient(fetcher).latest("CHII2") is None


def test_observation_age_is_computed_from_now():
    observation = parse_realtime(load_fixture("ndbc_chii2.txt"), "CHII2")
    assert observation.age > dt.timedelta(0)
