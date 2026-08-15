"""Terminal rendering.

The design goal is that the answer arrives before you have finished reading
the first line: verdict and score at the top, then *when* to go, then the
supporting detail. The hourly strip is the centerpiece — a colored bar per
hour of daylight, so the shape of the day is visible at a glance instead of
inferred from a table of numbers.
"""

from __future__ import annotations

import datetime as dt

from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..models import DayOutlook, Report, ScoredHour, Verdict
from ..timefmt import clock, day_label, duration_label, hour_label
from ..windows import sparkline

BAR_BLOCKS = "▁▂▃▄▅▆▇█"


def score_style(value: float, *, vetoed: bool = False) -> str:
    """Rich style for a score, matching the verdict colors."""
    return Verdict.from_score(value, vetoed=vetoed).color


def _bar(scored: ScoredHour) -> Text:
    index = round(max(0.0, min(10.0, scored.value)) / 10.0 * (len(BAR_BLOCKS) - 1))
    style = score_style(scored.value, vetoed=scored.score.vetoed)
    return Text(BAR_BLOCKS[index], style=style if scored.daylight else "grey37")


def hourly_strip(day: DayOutlook, *, label_every: int = 3) -> RenderableType:
    """A bar per daylight hour, with hour labels beneath.

    Falls back to the full 24 hours if the day has no daylight data at all
    (polar night, or a grid that only covers the small hours).
    """
    hours = day.daylight_hours or day.hours
    if not hours:
        return Text("no hourly data", style="grey62")

    bars = Text()
    labels = Text()
    for position, scored in enumerate(hours):
        bars.append_text(_bar(scored))
        bars.append(" ")
        if position % label_every == 0:
            labels.append(f"{hour_label(scored.time):<{2 * label_every}}", style="grey62")
    return Group(bars, labels)


def _window_table(day: DayOutlook) -> Table | None:
    if not day.windows:
        return None
    table = Table(box=None, pad_edge=False, show_header=True, header_style="grey62")
    table.add_column("window")
    table.add_column("for", justify="right")
    table.add_column("avg", justify="right")
    table.add_column("peak hour")
    for window in day.windows[:3]:
        peak = window.peak
        table.add_row(
            Text(window.describe(), style="bold"),
            duration_label(window.length_hours),
            Text(f"{window.mean_score:.1f}", style=score_style(window.mean_score)),
            f"{peak.hour.wind_phrase} at {hour_label(peak.time)}",
        )
    return table


def _conditions_line(day: DayOutlook) -> Text:
    peak = day.peak
    if peak is None:
        return Text("no forecast hours", style="grey62")
    hour = peak.hour
    text = Text()
    text.append("peak  ", style="grey62")
    text.append(hour.wind_phrase, style="bold")
    if hour.wave_ft is not None:
        text.append(f"  ·  {hour.wave_ft:.1f} ft seas")
    if hour.feels_like_f is not None:
        text.append(f"  ·  feels {hour.feels_like_f:.0f}°F")
    text.append(f"  ·  {hour.sky_phrase}")
    if hour.precip_pct:
        text.append(f"  ·  {hour.precip_pct:.0f}% precip")
    return text


def _sun_line(day: DayOutlook) -> Text:
    sun = day.sun
    if sun.sunrise is None or sun.sunset is None:
        return Text("")
    return Text(
        f"sun   {clock(sun.sunrise)} – {clock(sun.sunset)}  ({sun.daylight_hours:.1f} h of daylight)",
        style="grey62",
    )


def _explain_table(day: DayOutlook) -> Table | None:
    """Factor-by-factor arithmetic for the best hour of the day."""
    peak = day.peak
    if peak is None or not peak.score.factors:
        return None
    table = Table(
        box=None,
        pad_edge=False,
        title=f"why {peak.value:.1f}/10 at {hour_label(peak.time)}",
        title_justify="left",
        title_style="grey62",
        header_style="grey62",
    )
    table.add_column("factor")
    table.add_column("score", justify="right")
    table.add_column("weight", justify="right")
    table.add_column("reading")
    for factor in peak.score.factors:
        table.add_row(
            factor.name,
            Text(f"{factor.score:.2f}", style=score_style(factor.score * 10)),
            f"{factor.weight:g}",
            Text(factor.note, style="grey70"),
        )
    for veto in peak.score.vetoes:
        table.add_row(
            Text("veto", style="bold red"),
            Text(f"≤{veto.cap:.1f}", style="bold red"),
            "",
            Text(veto.reason, style="red"),
        )
    return table


def render_day(day: DayOutlook, *, explain: bool = False, today: dt.date | None = None) -> Panel:
    """One day as a bordered panel."""
    verdict = day.verdict
    heading = Text()
    heading.append(f"{day_label(day.date, today=today)}  ", style="bold")
    heading.append(f"{day.score:.1f}/10 ", style=verdict.color)
    heading.append(verdict.label, style=verdict.color)

    body: list[RenderableType] = [hourly_strip(day)]

    window = day.best_window
    if window:
        line = Text("go    ", style="grey62")
        line.append(window.describe(), style="bold bright_white")
        line.append(f"  ·  {duration_label(window.length_hours)} at {window.mean_score:.1f}/10")
        body.append(line)
    else:
        body.append(Text("go    nothing clears the threshold today", style="grey62"))

    body.append(_conditions_line(day))
    sun_line = _sun_line(day)
    if sun_line.plain:
        body.append(sun_line)

    windows = _window_table(day)
    if windows and len(day.windows) > 1:
        body.append(Text())
        body.append(windows)

    if explain:
        table = _explain_table(day)
        if table:
            body.append(Text())
            body.append(table)

    return Panel(Group(*body), title=heading, title_align="left", border_style=verdict.color, padding=(0, 1))


def render_report(report: Report, console: Console, *, explain: bool = False) -> None:
    """Print a full report for one spot."""
    spot = report.spot
    header = Text()
    header.append(f"⛵ {spot.name}", style="bold bright_white")
    if spot.region:
        header.append(f"  {spot.region}", style="grey62")
    header.append(f"   {report.profile_key} profile", style="grey50")
    console.print(header)
    if spot.blurb:
        console.print(Text(f"   {spot.blurb}", style="italic grey54"))

    if report.observation is not None:
        obs = report.observation
        age = obs.age.total_seconds() / 60
        console.print(
            Text(f"   buoy {obs.station}: {obs.describe()} ({age:.0f} min ago)", style="cyan")
        )

    for hazard in report.hazards:
        console.print(Text(f"   ⚠ {hazard.headline}", style="bold yellow"))

    for note in report.notes:
        console.print(Text(f"   · {note}", style="grey54"))

    console.print()
    for day in report.days:
        console.print(render_day(day, explain=explain, today=report.generated_at.date()))
    if not report.days:
        console.print(Text("   no forecast days available", style="grey62"))
    console.print()


def render_summary(reports: list[Report], console: Console) -> None:
    """A one-line-per-spot leaderboard, for when you are comparing places."""
    table = Table(title="Sailing outlook", box=None, header_style="grey62", title_style="bold", title_justify="left")
    table.add_column("spot")
    table.add_column("day")
    table.add_column("score", justify="right")
    table.add_column("verdict")
    table.add_column("window")
    table.add_column("shape")

    for report in sorted(reports, key=lambda r: -(r.best_day.score if r.best_day else 0)):
        day = report.best_day
        if day is None:
            table.add_row(report.spot.name, "—", "—", Text("no data", style="grey62"), "—", "")
            continue
        window = day.best_window
        table.add_row(
            Text(report.spot.name, style="bold"),
            day_label(day.date, today=report.generated_at.date()),
            Text(f"{day.score:.1f}", style=score_style(day.score)),
            Text(day.verdict.label, style=day.verdict.color),
            window.describe() if window else "—",
            Text(sparkline(day.daylight_hours or day.hours), style="cyan"),
        )
    console.print(table)
