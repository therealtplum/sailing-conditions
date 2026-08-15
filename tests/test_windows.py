"""Window search over scored hours."""

from __future__ import annotations

import datetime as dt

from sailing_conditions.windows import find_windows, sparkline
from tests.conftest import make_scored


def test_finds_the_contiguous_run_above_threshold():
    hours = [make_scored(h, v) for h, v in zip(range(8, 15), [3, 4, 7, 8, 9, 6, 2], strict=True)]
    windows = find_windows(hours, min_score=6.0)
    assert len(windows) == 1
    assert windows[0].length_hours == 4
    assert windows[0].describe() == "10am–2pm"


def test_a_gap_splits_the_window():
    hours = [make_scored(h, v) for h, v in zip(range(8, 15), [8, 8, 2, 8, 8, 8, 2], strict=True)]
    windows = find_windows(hours, min_score=6.0)
    assert [w.length_hours for w in windows] == [3, 2]


def test_missing_hours_break_contiguity():
    """A grid gap must not glue 9am and 2pm into one five-hour window."""
    hours = [make_scored(9, 8.0), make_scored(10, 8.0), make_scored(14, 8.0), make_scored(15, 8.0)]
    windows = find_windows(hours, min_score=6.0)
    assert len(windows) == 2
    assert all(w.length_hours == 2 for w in windows)


def test_short_runs_are_ignored():
    hours = [make_scored(h, v) for h, v in zip(range(8, 12), [2, 9, 2, 2], strict=True)]
    assert find_windows(hours, min_score=6.0, min_hours=2) == ()
    assert len(find_windows(hours, min_score=6.0, min_hours=1)) == 1


def test_night_hours_are_excluded_by_default():
    hours = [make_scored(h, 9.0, daylight=False) for h in range(1, 5)]
    assert find_windows(hours) == ()
    assert len(find_windows(hours, daylight_only=False)) == 1


def test_windows_are_ranked_best_first():
    hours = [make_scored(h, v) for h, v in zip(range(6, 16), [7, 7, 7, 2, 9, 9, 9, 2, 8, 8], strict=True)]
    windows = find_windows(hours, min_score=6.0)
    assert [round(w.mean_score, 1) for w in windows] == [9.0, 8.0, 7.0]


def test_window_reports_its_peak_hour():
    hours = [make_scored(10, 7.0), make_scored(11, 9.5), make_scored(12, 7.5)]
    window = find_windows(hours, min_score=6.0)[0]
    assert window.peak.value == 9.5
    assert window.peak.time.hour == 11
    assert window.end - window.start == dt.timedelta(hours=3)


def test_unsorted_input_is_handled():
    hours = [make_scored(12, 8.0), make_scored(10, 8.0), make_scored(11, 8.0)]
    windows = find_windows(hours, min_score=6.0)
    assert len(windows) == 1 and windows[0].length_hours == 3


def test_empty_input():
    assert find_windows([]) == ()
    assert sparkline([]) == ""


def test_sparkline_tracks_the_shape_of_the_day():
    hours = [make_scored(h, v) for h, v in zip(range(8, 13), [0, 2.5, 5, 7.5, 10], strict=True)]
    line = sparkline(hours)
    assert len(line) == 5
    assert line[0] == " " and line[-1] == "█"
    assert list(line) == sorted(line), "bars should grow with the score"
