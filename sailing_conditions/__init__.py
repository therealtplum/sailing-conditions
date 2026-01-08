"""sailing_conditions – multi-city sailing forecast CLI."""
from __future__ import annotations

from .cities import CITIES
from .cli import main
from .emoji import pick_weather_emoji
from .forecast import (
    chicago_forecast,
    find_best_sailing_window,
    grid_city_forecast,
    marine_city_forecast,
    week_forecast,
)
from .formatters import (
    build_email_html,
    format_json_output,
    format_slack_line_city,
    format_verbose_entry,
    format_week_summary,
)
from .parsers import compute_rating, compute_rating_breakdown, parse_sky, parse_waves, parse_wind
from .senders import post_slack, send_email_html
from .alerts import add_alert, check_alerts, list_alerts, remove_alert

__all__ = [
    "CITIES",
    "main",
    # Forecast functions
    "chicago_forecast",
    "marine_city_forecast",
    "grid_city_forecast",
    "week_forecast",
    "find_best_sailing_window",
    # Parsers
    "parse_wind",
    "parse_waves",
    "parse_sky",
    "compute_rating",
    "compute_rating_breakdown",
    # Formatting
    "pick_weather_emoji",
    "format_slack_line_city",
    "format_json_output",
    "format_verbose_entry",
    "format_week_summary",
    "build_email_html",
    # Senders
    "post_slack",
    "send_email_html",
    # Alerts
    "add_alert",
    "remove_alert",
    "list_alerts",
    "check_alerts",
]
