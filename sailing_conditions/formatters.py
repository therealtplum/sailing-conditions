"""Output formatters for Slack, email, JSON, and verbose modes."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


def format_slack_line_city(
    prefix_emoji: str,
    city: str,
    label: str,
    rating: int,
    wind_line: str,
    waves_line: str,
    sky_line: str,
    sailing: bool,
    suggestion: Optional[str],
    temp_f: Optional[int] = None,
    sun: Optional[dict] = None,
    best_window: Optional[dict] = None,
) -> str:
    """
    Format a single city forecast line for Slack.

    Args:
        prefix_emoji: Emoji prefix (e.g., "⛵ ☀")
        city: City name
        label: Day label (e.g., "Today")
        rating: Sailing rating (1-10)
        wind_line: Formatted wind string
        waves_line: Formatted waves string
        sky_line: Sky condition string
        sailing: Whether this is a sailing city
        suggestion: Activity suggestion for non-sailing cities
        temp_f: Temperature in Fahrenheit
        sun: Sun times dictionary
        best_window: Best sailing window info

    Returns:
        Formatted Slack message line
    """
    temp_str = f", {temp_f}°F" if temp_f is not None else ""

    if sailing:
        base = f"{prefix_emoji} {city} — {label}: {rating}/10{temp_str}. Wind {wind_line}, waves {waves_line}, {sky_line}."

        # Add best sailing window if available
        if best_window:
            base += f" Best: {best_window['start_time']}–{best_window['end_time']}."

        # Add sun times if available
        if sun and sun.get("sunrise") and sun.get("sunset"):
            base += f" ☀️ {sun['sunrise']}–{sun['sunset']}"

        return base

    return f"{prefix_emoji} {city} — {label}{temp_str}: {sky_line or '—'}. {suggestion or ''}".rstrip()


def format_verbose_entry(entry: Dict[str, Any]) -> str:
    """
    Format a forecast entry with detailed rating breakdown.

    Args:
        entry: Forecast dictionary with rating_breakdown

    Returns:
        Verbose formatted string
    """
    lines = [
        f"\n{'='*60}",
        f"{entry['prefix']} {entry['city']} — {entry['label']}",
        f"{'='*60}",
    ]

    # Main info
    temp_str = f" ({entry['temp_f']}°F)" if entry.get('temp_f') else ""
    lines.append(f"Rating: {entry['rating']}/10{temp_str}")
    lines.append(f"Wind: {entry['wind_line']}")
    lines.append(f"Waves: {entry['waves_line']}")
    lines.append(f"Sky: {entry['sky_line']}")

    # Sun times
    if entry.get("sun"):
        sun = entry["sun"]
        if sun.get("sunrise") and sun.get("sunset"):
            lines.append(f"Daylight: {sun['sunrise']} – {sun['sunset']} ({sun['daylight_hours']}h)")

    # Best window
    if entry.get("best_window"):
        bw = entry["best_window"]
        lines.append(f"Best Window: {bw['start_time']}–{bw['end_time']} (avg {bw['avg_rating']}/10)")

    # Rating breakdown
    if entry.get("rating_breakdown"):
        rb = entry["rating_breakdown"]
        lines.append("")
        lines.append("Rating Breakdown:")
        lines.append(f"  Base score: {rb['base']}")
        if rb.get("wind_reason"):
            adj = f"+{rb['wind_adj']}" if rb['wind_adj'] >= 0 else str(rb['wind_adj'])
            lines.append(f"  Wind: {adj} ({rb['wind_reason']})")
        if rb.get("wave_reason"):
            adj = f"+{rb['wave_adj']}" if rb['wave_adj'] >= 0 else str(rb['wave_adj'])
            lines.append(f"  Waves: {adj} ({rb['wave_reason']})")
        if rb.get("sky_reason"):
            adj = f"+{rb['sky_adj']}" if rb['sky_adj'] >= 0 else str(rb['sky_adj'])
            lines.append(f"  Sky: {adj} ({rb['sky_reason']})")
        lines.append(f"  Raw score: {rb['raw']} → Final: {rb['final']}")

    return "\n".join(lines)


def format_week_summary(entries: List[Dict[str, Any]], city: str) -> str:
    """
    Format a week forecast summary.

    Args:
        entries: List of forecast dictionaries for the week
        city: City name

    Returns:
        Formatted week summary string
    """
    if not entries:
        return f"No forecast data available for {city}."

    lines = [
        f"\n{'='*60}",
        f"📅 7-Day Forecast: {city}",
        f"{'='*60}",
    ]

    # Find best day
    best_day = max(entries, key=lambda x: x["rating"])

    for entry in entries:
        temp_str = f" {entry['temp_f']}°F" if entry.get('temp_f') else ""
        star = " ⭐ BEST" if entry == best_day else ""
        lines.append(
            f"{entry['prefix']} {entry['label']}: {entry['rating']}/10{temp_str} — "
            f"{entry['sky_line']}{star}"
        )

    # Summary
    avg_rating = sum(e["rating"] for e in entries) / len(entries)
    lines.append("")
    lines.append(f"Best day: {best_day['label']} ({best_day['rating']}/10)")
    lines.append(f"Average rating: {avg_rating:.1f}/10")

    return "\n".join(lines)


def format_json_output(entries: List[Dict[str, Any]], pretty: bool = True) -> str:
    """
    Format forecast entries as JSON.

    Args:
        entries: List of forecast dictionaries
        pretty: Whether to pretty-print the JSON

    Returns:
        JSON string
    """
    # Clean up entries for JSON output
    clean_entries = []
    for entry in entries:
        clean = {
            "city": entry["city"],
            "city_key": entry.get("city_key"),
            "label": entry["label"],
            "date": entry.get("date"),
            "rating": entry["rating"],
            "wind": entry["wind_line"],
            "waves": entry["waves_line"],
            "sky": entry["sky_line"],
            "sailing": entry["sailing"],
        }

        # Add optional fields
        if entry.get("temp_f") is not None:
            clean["temperature"] = {
                "fahrenheit": entry["temp_f"],
                "celsius": entry.get("temp_c"),
            }

        if entry.get("wind_kt"):
            clean["wind_kt"] = entry["wind_kt"]

        if entry.get("waves_ft"):
            clean["waves_ft"] = entry["waves_ft"]

        if entry.get("sun"):
            clean["sun"] = entry["sun"]

        if entry.get("best_window"):
            clean["best_window"] = entry["best_window"]

        if entry.get("rating_breakdown"):
            clean["rating_breakdown"] = entry["rating_breakdown"]

        clean_entries.append(clean)

    output = {
        "forecasts": clean_entries,
        "count": len(clean_entries),
    }

    if pretty:
        return json.dumps(output, indent=2, default=str)
    return json.dumps(output, default=str)


def build_email_html(entries: List[dict], date_str: str) -> str:
    """
    Build HTML email content from forecast entries.

    Args:
        entries: List of forecast dictionaries
        date_str: Formatted date string for the header

    Returns:
        Complete HTML email string
    """

    def color(r: int) -> str:
        """Get color based on rating."""
        if r >= 8:
            return "#16a34a"
        if r >= 5:
            return "#eab308"
        return "#dc2626"

    rows = []
    for e in entries:
        temp_str = f"<br><small>{e.get('temp_f', '—')}°F</small>" if e.get('temp_f') else ""
        sun_str = ""
        if e.get("sun") and e["sun"].get("sunrise"):
            sun_str = f"<br><small>☀️ {e['sun']['sunrise']}–{e['sun']['sunset']}</small>"

        rows.append(f"""
        <tr>
          <td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;">{e['prefix']} {e['city']}{temp_str}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;">{e['label']}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;">
            <span style="display:inline-block;padding:2px 8px;border-radius:999px;background:{color(e['rating'])};color:#fff;font-weight:700;">{e['rating']}/10</span>
          </td>
          <td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;">{e['wind_line']}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;">{e['waves_line']}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;">{e['sky_line']}{sun_str}</td>
        </tr>""")

    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f6f7fb;font-family:Arial,Helvetica,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f6f7fb;padding:20px 0;">
    <tr><td align="center">
      <table width="880" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;border:1px solid #e5e7eb;">
        <tr><td style="background:#0ea5e9;color:#fff;padding:16px 20px;font-size:18px;font-weight:bold;">
          Sailing Quick Hits — {date_str}
        </td></tr>
        <tr><td style="padding:8px 0 0 0;">
          <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
            <thead>
              <tr>
                <th align="left" style="padding:10px;border-bottom:2px solid #e5e7eb;">City</th>
                <th align="left" style="padding:10px;border-bottom:2px solid #e5e7eb;">Day</th>
                <th align="left" style="padding:10px;border-bottom:2px solid #e5e7eb;">Rating</th>
                <th align="left" style="padding:10px;border-bottom:2px solid #e5e7eb;">Wind</th>
                <th align="left" style="padding:10px;border-bottom:2px solid #e5e7eb;">Waves</th>
                <th align="left" style="padding:10px;border-bottom:2px solid #e5e7eb;">Sky</th>
              </tr>
            </thead>
            <tbody>
              {''.join(rows) if rows else '<tr><td colspan="6" style="padding:10px;">No data.</td></tr>'}
            </tbody>
          </table>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""
