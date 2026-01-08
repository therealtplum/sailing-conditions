#!/usr/bin/env python3
"""Command-line interface for sailing-conditions."""
from __future__ import annotations

import argparse
import calendar
import os
import random
import sys
from datetime import date, timedelta
from typing import List

from .alerts import add_alert, check_alerts, format_alerts_list, list_alerts, remove_alert
from .cities import CITIES
from .config import DEFAULT_KEYS, RAINY_WORDS, SEVERE_WORDS
from .fetchers import fetch_city_marine_text
from .forecast import (
    chicago_forecast,
    find_best_sailing_window,
    grid_city_forecast,
    marine_city_forecast,
    week_forecast,
    _pick_present_day_label,
)
from .formatters import (
    build_email_html,
    format_json_output,
    format_slack_line_city,
    format_verbose_entry,
    format_week_summary,
)
from .senders import post_slack, send_email_html

# Suggestions for non-sailing cities
OUTDOOR_SUGG = [
    "find a farmer's market",
    "hit a park picnic",
    "catch a baseball game",
    "walk a new waterfront path",
    "try a rooftop spot",
    "rent a bike and explore",
]
INDOOR_SUGG = [
    "museum hop",
    "duck into a matinee",
    "bookstore + coffee crawl",
    "try an indoor food hall",
    "visit a gallery",
    "karaoke night",
]
NEUTRAL_SUGG = [
    "discover a neighborhood bakery",
    "brunch somewhere new",
    "cozy café + people-watch",
    "take a cooking class",
    "check a pop-up market",
]


def _is_rainy(sky: str | None) -> bool:
    """Check if sky description indicates rain."""
    return bool(sky) and any(k in sky.lower() for k in RAINY_WORDS)


def pick_suggestion(city_label: str, sky: str | None) -> str:
    """
    Pick an activity suggestion based on weather conditions.

    Args:
        city_label: City name
        sky: Sky/weather description

    Returns:
        Activity suggestion string
    """
    stable = os.environ.get("SUGGESTION_MODE", "").lower() == "stable"
    rng = random.Random(f"{city_label}-{date.today().isoformat()}") if stable else random.SystemRandom()

    if sky and any(k in sky.lower() for k in SEVERE_WORDS):
        return "Best bet: stay indoors and keep an eye on the radar."
    if _is_rainy(sky):
        return "Aw shoot — " + rng.choice(INDOOR_SUGG)
    if any(k in (sky or "").lower() for k in ["sunny", "clear"]):
        return rng.choice(OUTDOOR_SUGG)
    return rng.choice(NEUTRAL_SUGG)


def in_season(d: date) -> bool:
    """
    Check if a date falls within the Chicago sailing season (Memorial Day to Labor Day).

    Args:
        d: Date to check

    Returns:
        True if date is in season, False otherwise
    """
    last_may_day = max(day for day in range(31, 24, -1) if date(d.year, 5, day).weekday() == calendar.MONDAY)
    memorial_day = date(d.year, 5, last_may_day)
    first_sept_monday = next(day for day in range(1, 8) if date(d.year, 9, day).weekday() == calendar.MONDAY)
    labor_day = date(d.year, 9, first_sept_monday)
    return memorial_day <= d <= labor_day


def _resolve_city_selection(args: argparse.Namespace, unknown: List[str]) -> List[str]:
    """
    Resolve which cities to include based on command-line arguments.

    Priority order:
    1. --only flag (comma-separated list)
    2. Unknown flags like --miami or legacy flags like --chicago
    3. --all-cities flag
    4. Default cities

    Args:
        args: Parsed command-line arguments
        unknown: List of unknown arguments

    Returns:
        List of city keys to process
    """
    # Priority: --only > unknown --<key> flags & legacy flags > --all-cities > default
    if args.only:
        sel = [k.strip().lower() for k in args.only.split(",") if k.strip()]
        valid_cities = [k for k in sel if k in CITIES]
        if valid_cities:
            return valid_cities
        # If no valid cities found, warn and use defaults
        invalid = [k for k in sel if k not in CITIES]
        if invalid:
            print(f"[warn] Invalid city keys ignored: {', '.join(invalid)}", file=sys.stderr)
        return DEFAULT_KEYS.copy()

    # unknown flags like --miami
    unk_keys = []
    for u in unknown:
        if u.startswith("--") and len(u) > 2 and "=" not in u:
            key = u[2:].lower().replace("-", "")
            if key in CITIES:
                unk_keys.append(key)

    legacy = []
    if args.chicago:
        legacy.append("chicago")
    if args.nyc:
        legacy.append("nyc")
    if args.philly:
        legacy.append("philly")
    if args.kc:
        legacy.append("kc")
    if args.slc:
        legacy.append("slc")

    candidates = list(dict.fromkeys(unk_keys + legacy))  # preserve order
    if args.all_cities:
        return list(CITIES.keys())
    if candidates:
        return candidates
    return DEFAULT_KEYS.copy()


def main() -> int:
    """
    Main CLI entry point for sailing conditions forecast tool.

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    parser = argparse.ArgumentParser(
        description="Multi-city Sailing Quick Hits",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --today --only chicago --slack
  %(prog)s --tomorrow --all-cities --email
  %(prog)s --weekend --miami --nyc
  %(prog)s --week --chicago --format json
  %(prog)s --today --chicago --verbose
  %(prog)s --alert-add --city chicago --min-rating 8
  %(prog)s --alert-list
  %(prog)s --all
        """,
    )

    # Day selection (mutually exclusive)
    day = parser.add_mutually_exclusive_group()
    day.add_argument("--today", action="store_true", help="Use today's forecast (default)")
    day.add_argument("--tomorrow", action="store_true", help="Use tomorrow's forecast")
    day.add_argument("--weekend", action="store_true", help="Use Saturday & Sunday")
    day.add_argument("--week", action="store_true", help="Show 7-day forecast")

    # Output format
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed rating breakdown")

    # Delivery (independent)
    parser.add_argument("--email", action="store_true", help="Send to Email")
    parser.add_argument("--slack", action="store_true", help="Send to Slack")
    parser.add_argument("--all-delivery", action="store_true", help="Send to both Email and Slack")
    parser.add_argument("--all", action="store_true", help="Alias for both --all-cities and --all-delivery")
    parser.add_argument("--no-send", action="store_true", help="Don't send, just print output")

    # City selection
    parser.add_argument("--all-cities", action="store_true", help="Include every city in CITIES")
    parser.add_argument("--only", type=str, help="Comma list of city keys (e.g., miami,nyc,chicago)")
    parser.add_argument("--chicago", action="store_true")
    parser.add_argument("--nyc", action="store_true")
    parser.add_argument("--philly", action="store_true")
    parser.add_argument("--kc", action="store_true")
    parser.add_argument("--slc", action="store_true")

    # Alert management
    alert_group = parser.add_argument_group("Alert Management")
    alert_group.add_argument("--alert-add", action="store_true", help="Add a new alert")
    alert_group.add_argument("--alert-remove", type=str, metavar="ID", help="Remove an alert by ID")
    alert_group.add_argument("--alert-list", action="store_true", help="List all alerts")
    alert_group.add_argument("--alert-check", action="store_true", help="Check alerts against current conditions")
    alert_group.add_argument("--city", type=str, help="City key for alert (with --alert-add)")
    alert_group.add_argument("--min-rating", type=int, default=7, help="Minimum rating for alert (default: 7)")

    args, unknown = parser.parse_known_args()

    # Handle alert commands
    if args.alert_list:
        alerts = list_alerts()
        print(format_alerts_list(alerts))
        return 0

    if args.alert_add:
        if not args.city:
            print("[error] --city required with --alert-add", file=sys.stderr)
            return 1
        if args.city not in CITIES:
            print(f"[error] Invalid city key: {args.city}", file=sys.stderr)
            return 1
        alert = add_alert(
            city_key=args.city,
            min_rating=args.min_rating,
            notify_slack=args.slack or args.all_delivery or True,
            notify_email=args.email or args.all_delivery,
        )
        print(f"[info] Alert created: {alert['id']}")
        print(f"  City: {args.city}, Min rating: {args.min_rating}")
        return 0

    if args.alert_remove:
        if remove_alert(args.alert_remove):
            print(f"[info] Alert removed: {args.alert_remove}")
            return 0
        print(f"[error] Alert not found: {args.alert_remove}", file=sys.stderr)
        return 1

    # --all means both
    if args.all:
        args.all_cities = True
        args.all_delivery = True

    # Delivery defaults: if nothing specified and not no_send, send both
    explicit = args.email or args.slack or args.all_delivery or args.no_send
    send_email_flag = (args.email or args.all_delivery) and not args.no_send
    send_slack_flag = (args.slack or args.all_delivery) and not args.no_send

    # If no explicit delivery and not no_send, default to both (unless JSON format)
    if not explicit and args.format != "json":
        send_email_flag = True
        send_slack_flag = True

    # Cities
    sel = _resolve_city_selection(args, unknown)

    # Labels
    today_dt = date.today()
    tomorrow_dt = today_dt + timedelta(days=1)

    if args.week:
        # 7-day forecast mode
        return _handle_week_forecast(sel, args)

    if args.weekend:
        delta_to_sat = (5 - today_dt.weekday()) % 7
        sat_dt = today_dt + timedelta(days=delta_to_sat)
        sun_dt = sat_dt + timedelta(days=1)
        labels = ["SATURDAY", "SUNDAY"]
        label_dates = [sat_dt, sun_dt]
    elif args.tomorrow:
        labels = [tomorrow_dt.strftime("%A").upper()]
        label_dates = [tomorrow_dt]
    else:
        labels = ["REST OF TODAY", "TODAY"]
        label_dates = [today_dt]

    # Chicago season gate
    if "chicago" in sel and not any(in_season(d) for d in label_dates):
        if sel == ["chicago"]:
            print("[info] Chicago out of season; no message sent.")
            return 0
        sel = [k for k in sel if k != "chicago"]

    # Build entries
    entries = []
    include_details = args.verbose or args.format == "json"

    for key in sel:
        if key not in CITIES:
            print(f"[warn] Skipping invalid city key: {key}", file=sys.stderr)
            continue

        # Choose concrete "today" label that actually exists for marine products
        if labels == ["REST OF TODAY", "TODAY"]:
            if CITIES[key]["type"] == "marine":
                mt = fetch_city_marine_text(CITIES[key].get("marine_zones") or [])
                use_label = _pick_present_day_label(mt) if mt else "TODAY"
            else:
                use_label = "TODAY"
            entries_labels = [use_label]
        else:
            entries_labels = labels

        for lab in entries_labels:
            try:
                meta = CITIES[key]
                if key == "chicago":
                    e = chicago_forecast(lab, include_details=include_details)
                elif meta["type"] == "marine":
                    e = marine_city_forecast(key, lab, include_details=include_details)
                else:
                    e = grid_city_forecast(key, lab, include_details=include_details)

                # Add best sailing window for today
                if lab.upper() in ("TODAY", "REST OF TODAY") and e.get("sailing"):
                    best_window = find_best_sailing_window(key)
                    if best_window:
                        e["best_window"] = best_window

                entries.append(e)
            except Exception as ex:
                print(f"[warn] Failed to fetch forecast for {key} ({lab}): {ex}", file=sys.stderr)
                # Continue with other cities even if one fails

    # Check alerts if requested
    if args.alert_check:
        triggered = check_alerts(entries)
        if triggered:
            print(f"[info] {len(triggered)} alert(s) triggered")
        else:
            print("[info] No alerts triggered")

    # Output based on format
    if args.format == "json":
        output = format_json_output(entries)
        print(output)
        return 0

    if args.verbose:
        for e in entries:
            print(format_verbose_entry(e))
        return 0

    # Slack text
    lines = [
        format_slack_line_city(
            e["prefix"],
            e["city"],
            e["label"],
            e["rating"],
            e["wind_line"],
            e["waves_line"],
            e["sky_line"],
            e["sailing"],
            None if e["sailing"] else pick_suggestion(e["city"], e["sky_line"]),
            temp_f=e.get("temp_f"),
            sun=e.get("sun"),
            best_window=e.get("best_window"),
        )
        for e in entries
    ]
    slack_text = "\n".join(lines) if lines else "No data."

    # Email - cross-platform date formatting
    try:
        # Try Unix-style format first (%-d removes leading zero)
        date_str = today_dt.strftime("%a %b %-d, %Y")
    except ValueError:
        # Windows doesn't support %-d, use %#d or fallback to %d
        try:
            date_str = today_dt.strftime("%a %b %#d, %Y")
        except ValueError:
            # Final fallback: use %d (may have leading zero)
            date_str = today_dt.strftime("%a %b %d, %Y")
    subject = "Sailing Quick Hits — Multi-City"
    text_fallback = "\n".join(f"{e['prefix']} {e['city']} — {e['quick']}" for e in entries)
    html = build_email_html(entries, date_str)

    # Send
    errors = []
    if send_email_flag:
        try:
            send_email_html(subject, html, text_fallback)
        except Exception as e:
            errors.append(f"Email send failed: {e}")
            print(f"[error] Email send failed: {e}", file=sys.stderr)

    if send_slack_flag:
        try:
            post_slack(slack_text)
        except Exception as e:
            errors.append(f"Slack send failed: {e}")
            print(f"[error] Slack send failed: {e}", file=sys.stderr)

    # Print once
    print(slack_text)

    # Return non-zero exit code if there were errors
    return 1 if errors else 0


def _handle_week_forecast(sel: List[str], args: argparse.Namespace) -> int:
    """
    Handle 7-day forecast mode.

    Args:
        sel: List of city keys
        args: Parsed arguments

    Returns:
        Exit code
    """
    all_entries = []

    for key in sel:
        if key not in CITIES:
            print(f"[warn] Skipping invalid city key: {key}", file=sys.stderr)
            continue

        try:
            entries = week_forecast(key, include_details=args.verbose or args.format == "json")
            all_entries.extend(entries)

            if args.format == "text" and not args.verbose:
                print(format_week_summary(entries, CITIES[key]["label"]))
        except Exception as ex:
            print(f"[warn] Failed to fetch week forecast for {key}: {ex}", file=sys.stderr)

    if args.format == "json":
        print(format_json_output(all_entries))
        return 0

    if args.verbose:
        for e in all_entries:
            print(format_verbose_entry(e))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
