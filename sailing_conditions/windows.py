"""Finding sailable windows in a scored day.

The interesting question is not "how is Saturday?" but "when on Saturday?".
A day whose mean score is 5.5 might be unsailable all morning and glorious
from two o'clock — the mean hides exactly the information you wanted.

The search is a linear scan for maximal runs of consecutive hours at or
above a threshold, which is O(n) and, more importantly, easy to reason
about: a window is *every* qualifying hour in a row, never a subset chosen
to flatter the average.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Sequence

from .models import ScoredHour, Window

DEFAULT_MIN_SCORE = 6.0
DEFAULT_MIN_HOURS = 2


def find_windows(
    hours: Iterable[ScoredHour],
    *,
    min_score: float = DEFAULT_MIN_SCORE,
    min_hours: int = DEFAULT_MIN_HOURS,
    daylight_only: bool = True,
) -> tuple[Window, ...]:
    """Group consecutive qualifying hours into windows, best first.

    Args:
        hours: Scored hours, any order (they are sorted internally).
        min_score: Lowest score an hour may have and still qualify.
        min_hours: Shortest run worth reporting. Rigging the boat for a
            single good hour is rarely worth it.
        daylight_only: Skip hours when the sun is down.

    Returns:
        Windows sorted by mean score descending, ties broken by duration
        then by start time, so the first element is the one to sail.
    """
    ordered = sorted(hours, key=lambda h: h.time)
    runs: list[list[ScoredHour]] = []
    current: list[ScoredHour] = []

    for scored in ordered:
        qualifies = scored.value >= min_score and (scored.daylight or not daylight_only)
        contiguous = bool(current) and scored.time - current[-1].time == dt.timedelta(hours=1)
        if qualifies and (contiguous or not current):
            current.append(scored)
            continue
        if current:
            runs.append(current)
        current = [scored] if qualifies else []
    if current:
        runs.append(current)

    windows = [Window(tuple(run)) for run in runs if len(run) >= min_hours]
    windows.sort(key=lambda w: (-w.mean_score, -w.length_hours, w.start))
    return tuple(windows)


def best_window(
    hours: Sequence[ScoredHour],
    *,
    min_score: float = DEFAULT_MIN_SCORE,
    min_hours: int = DEFAULT_MIN_HOURS,
    daylight_only: bool = True,
) -> Window | None:
    """Return the single best window, or ``None`` if nothing qualifies."""
    found = find_windows(
        hours,
        min_score=min_score,
        min_hours=min_hours,
        daylight_only=daylight_only,
    )
    return found[0] if found else None


def sparkline(hours: Sequence[ScoredHour], *, blocks: str = " ▁▂▃▄▅▆▇█") -> str:
    """Render scores as a one-line Unicode bar chart.

    Each character is one hour, height proportional to score. Handy in a
    terminal, a Slack message, or a commit message.
    """
    if not hours:
        return ""
    steps = len(blocks) - 1
    out = []
    for scored in sorted(hours, key=lambda h: h.time):
        index = round(max(0.0, min(10.0, scored.value)) / 10.0 * steps)
        out.append(blocks[index])
    return "".join(out)
