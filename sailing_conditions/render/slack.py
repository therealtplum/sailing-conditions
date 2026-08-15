"""Slack rendering — Block Kit blocks plus a plain-text fallback.

A notification is read on a phone, at a glance, usually while doing
something else. So it leads with the decision (go / don't, when, how much
breeze) and keeps the supporting numbers to one line.
"""

from __future__ import annotations

from typing import Any

from ..models import Report, Verdict
from ..timefmt import day_label, duration_label
from ..windows import sparkline

VERDICT_EMOJI = {
    Verdict.EPIC: ":sailboat:",
    Verdict.GOOD: ":sailboat:",
    Verdict.MARGINAL: ":neutral_face:",
    Verdict.POOR: ":umbrella:",
    Verdict.NO_GO: ":no_entry:",
}


def fallback_text(report: Report) -> str:
    """Single-line summary used as the notification preview."""
    return report.headline()


def report_blocks(report: Report, *, max_days: int = 3) -> list[dict[str, Any]]:
    """Render one report as Slack Block Kit blocks."""
    day = report.today
    verdict = day.verdict if day else Verdict.NO_GO
    title = f"{VERDICT_EMOJI[verdict]}  {report.spot.name} — {verdict.label}"

    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": title, "emoji": True}}
    ]

    if day is None:
        blocks.append(_section("No forecast data available."))
        return blocks

    lines = []
    for outlook in report.days[:max_days]:
        window = outlook.best_window
        when = f"*{window.describe()}* · {duration_label(window.length_hours)}" if window else "_no window_"
        shape = sparkline(outlook.daylight_hours or outlook.hours)
        lines.append(
            f"*{day_label(outlook.date, today=report.generated_at.date())}* "
            f"`{outlook.score:>4.1f}` {outlook.verdict.label.lower()} — {when}  `{shape}`"
        )
    blocks.append(_section("\n".join(lines)))

    peak = day.peak
    if peak is not None:
        detail = f"*Peak:* {peak.hour.describe()}"
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": detail}]})

    if report.observation is not None:
        obs = report.observation
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Buoy {obs.station}:* {obs.describe()} "
                        f"({obs.age.total_seconds() / 60:.0f} min ago)",
                    }
                ],
            }
        )

    for hazard in report.hazards:
        blocks.append(_section(f":warning: *{hazard.event}* — {hazard.headline}"))

    footer = f"{report.spot.region or report.timezone} · {report.profile_key} profile"
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": footer}]})
    return blocks


def digest_blocks(reports: list[Report]) -> list[dict[str, Any]]:
    """Render several reports as one message, best spot first."""
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": "⛵ Sailing outlook", "emoji": True}}
    ]
    ranked = sorted(reports, key=lambda r: -(r.best_day.score if r.best_day else 0.0))
    for report in ranked:
        day = report.best_day
        if day is None:
            blocks.append(_section(f"*{report.spot.name}* — no data"))
            continue
        window = day.best_window
        when = f" · {window.describe()}" if window else ""
        blocks.append(
            _section(
                f"*{report.spot.name}* `{day.score:.1f}` {day.verdict.label.lower()}"
                f" · {day_label(day.date, today=report.generated_at.date())}{when}\n"
                f"`{sparkline(day.daylight_hours or day.hours)}`"
            )
        )
    return blocks


def _section(markdown: str) -> dict[str, Any]:
    return {"type": "section", "text": {"type": "mrkdwn", "text": markdown}}
