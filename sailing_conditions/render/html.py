"""HTML rendering for email.

Email clients are a hostile rendering target: no external CSS, no flexbox
worth trusting, and a decent chance the whole thing is read on a phone.
So this is tables and inline styles, deliberately — and every value that
could contain forecast text is escaped.
"""

from __future__ import annotations

import datetime as dt
from html import escape

from ..models import DayOutlook, Report, Verdict
from ..timefmt import clock, day_label, duration_label, long_date

VERDICT_COLORS = {
    Verdict.EPIC: "#15803d",
    Verdict.GOOD: "#16a34a",
    Verdict.MARGINAL: "#ca8a04",
    Verdict.POOR: "#ea580c",
    Verdict.NO_GO: "#dc2626",
}


def _pill(text: str, color: str) -> str:
    return (
        f'<span style="display:inline-block;padding:2px 10px;border-radius:999px;'
        f'background:{color};color:#fff;font-weight:700;font-size:13px;">{escape(text)}</span>'
    )


def _bar(day: DayOutlook) -> str:
    """A tiny inline bar chart of the day, built from table cells."""
    hours = day.daylight_hours or day.hours
    if not hours:
        return ""
    cells = []
    for scored in hours:
        height = max(2, round(scored.value / 10 * 28))
        color = VERDICT_COLORS[scored.score.verdict]
        cells.append(
            f'<td style="vertical-align:bottom;padding:0 1px;">'
            f'<div style="width:8px;height:{height}px;background:{color};border-radius:2px;"></div>'
            f"</td>"
        )
    labels = "".join(
        f'<td style="font-size:9px;color:#6b7280;text-align:center;">'
        f"{scored.time.strftime('%I').lstrip('0') if index % 3 == 0 else ''}</td>"
        for index, scored in enumerate(hours)
    )
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">'
        f"<tr>{''.join(cells)}</tr><tr>{labels}</tr></table>"
    )


def _day_row(day: DayOutlook, today: dt.date | None) -> str:
    window = day.best_window
    when = (
        f"{escape(window.describe())} · {duration_label(window.length_hours)}"
        if window
        else '<span style="color:#9ca3af;">no window</span>'
    )
    peak = day.peak
    detail = escape(peak.hour.describe()) if peak else "—"
    sun = ""
    if day.sun.sunrise and day.sun.sunset:
        sun = f"{clock(day.sun.sunrise)} – {clock(day.sun.sunset)}"
    return f"""
      <tr>
        <td style="padding:12px 10px;border-bottom:1px solid #e5e7eb;font-weight:600;">
          {escape(day_label(day.date, today=today))}
          <div style="font-weight:400;font-size:11px;color:#6b7280;">{escape(sun)}</div>
        </td>
        <td style="padding:12px 10px;border-bottom:1px solid #e5e7eb;">
          {_pill(f"{day.score:.1f}", VERDICT_COLORS[day.verdict])}
          <div style="font-size:11px;color:#6b7280;margin-top:4px;">{escape(day.verdict.label)}</div>
        </td>
        <td style="padding:12px 10px;border-bottom:1px solid #e5e7eb;">{when}</td>
        <td style="padding:12px 10px;border-bottom:1px solid #e5e7eb;color:#374151;">{detail}</td>
        <td style="padding:12px 10px;border-bottom:1px solid #e5e7eb;">{_bar(day)}</td>
      </tr>"""


def report_section(report: Report) -> str:
    """One spot's card, for embedding in a digest."""
    today = report.generated_at.date()
    hazards = "".join(
        f'<div style="margin:6px 0;padding:8px 10px;background:#fef2f2;border-left:3px solid #dc2626;'
        f'color:#7f1d1d;font-size:13px;">⚠ {escape(h.headline)}</div>'
        for h in report.hazards
    )
    notes = "".join(
        f'<div style="font-size:12px;color:#6b7280;margin-top:4px;">{escape(note)}</div>'
        for note in report.notes
    )
    observation = ""
    if report.observation is not None:
        obs = report.observation
        observation = (
            f'<div style="font-size:12px;color:#0e7490;margin-top:6px;">'
            f"Buoy {escape(obs.station)}: {escape(obs.describe())}</div>"
        )
    rows = "".join(_day_row(day, today) for day in report.days)
    if not rows:
        rows = '<tr><td colspan="5" style="padding:12px 10px;color:#6b7280;">No forecast data.</td></tr>'

    return f"""
    <tr><td style="padding:18px 20px 0 20px;">
      <div style="font-size:17px;font-weight:700;color:#0f172a;">{escape(report.spot.name)}
        <span style="font-weight:400;font-size:13px;color:#6b7280;"> {escape(report.spot.region)}</span>
      </div>
      <div style="font-size:12px;color:#6b7280;">{escape(report.spot.blurb)}</div>
      {observation}{hazards}{notes}
      <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin-top:10px;">
        <thead><tr style="font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#6b7280;">
          <th align="left" style="padding:6px 10px;border-bottom:2px solid #e5e7eb;">Day</th>
          <th align="left" style="padding:6px 10px;border-bottom:2px solid #e5e7eb;">Score</th>
          <th align="left" style="padding:6px 10px;border-bottom:2px solid #e5e7eb;">Window</th>
          <th align="left" style="padding:6px 10px;border-bottom:2px solid #e5e7eb;">Peak conditions</th>
          <th align="left" style="padding:6px 10px;border-bottom:2px solid #e5e7eb;">Shape of the day</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </td></tr>"""


def build_email(reports: list[Report], *, subject: str | None = None) -> str:
    """Render a complete HTML email for one or more spots."""
    today = reports[0].generated_at.date() if reports else None
    heading = subject or "Sailing conditions"
    date_line = long_date(today) if today else ""
    sections = "".join(report_section(report) for report in reports)
    profile = reports[0].profile_key if reports else ""

    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:24px 0;">
    <tr><td align="center">
      <table width="720" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;border:1px solid #e2e8f0;max-width:720px;">
        <tr><td style="background:#0f172a;color:#fff;padding:18px 20px;border-radius:12px 12px 0 0;">
          <div style="font-size:19px;font-weight:700;">⛵ {escape(heading)}</div>
          <div style="font-size:12px;color:#94a3b8;">{escape(date_line)} · {escape(profile)} profile</div>
        </td></tr>
        {sections}
        <tr><td style="padding:16px 20px;color:#94a3b8;font-size:11px;border-top:1px solid #e2e8f0;">
          Forecast data from NOAA/NWS and NDBC. Scores are advisory only — check the official
          marine forecast before you leave the dock.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def plain_text(reports: list[Report]) -> str:
    """Plain-text alternative part for the same email."""
    lines = []
    for report in reports:
        lines.append(report.headline())
        for day in report.days:
            window = day.best_window
            when = f" best {window.describe()}" if window else " no window"
            lines.append(
                f"  {day_label(day.date, today=report.generated_at.date())}: "
                f"{day.score:.1f}/10 {day.verdict.label}.{when}"
            )
        for hazard in report.hazards:
            lines.append(f"  ! {hazard.headline}")
    return "\n".join(lines)
