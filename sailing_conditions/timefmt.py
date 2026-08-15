"""Small, portable time formatting helpers.

``%-I`` (strip leading zero) is a glibc extension: it raises on Windows and
silently differs on some libcs. These helpers do the stripping by hand so
output is identical on every platform.
"""

from __future__ import annotations

import datetime as dt


def hour_label(when: dt.datetime) -> str:
    """``3pm`` — whole-hour label."""
    return when.strftime("%I%p").lstrip("0").lower()


def clock(when: dt.datetime) -> str:
    """``5:16am`` — minute-precision clock time."""
    return when.strftime("%I:%M%p").lstrip("0").lower()


def day_label(day: dt.date, *, today: dt.date | None = None) -> str:
    """``Today`` / ``Tomorrow`` / ``Sat Aug 22`` depending on distance."""
    today = today or dt.date.today()
    delta = (day - today).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Tomorrow"
    return day.strftime("%a %b ") + str(day.day)


def long_date(day: dt.date) -> str:
    """``Sat Aug 22, 2026`` — used in email headers."""
    return day.strftime("%a %b ") + f"{day.day}, {day.year}"


def duration_label(hours: float) -> str:
    """``3h 30m`` from a fractional hour count."""
    whole = int(hours)
    minutes = round((hours - whole) * 60)
    if minutes == 60:
        whole, minutes = whole + 1, 0
    return f"{whole}h" if minutes == 0 else f"{whole}h {minutes}m"
