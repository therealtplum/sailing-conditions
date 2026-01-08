"""Alert notification system for sailing conditions."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

from .config import ALERTS_FILE
from .senders import post_slack, send_email_html


def load_alerts() -> List[Dict[str, Any]]:
    """
    Load alerts from the alerts file.

    Returns:
        List of alert configurations
    """
    if not os.path.exists(ALERTS_FILE):
        return []

    try:
        with open(ALERTS_FILE, "r") as f:
            data = json.load(f)
            return data.get("alerts", [])
    except Exception as e:
        print(f"[warn] Failed to load alerts: {e}", file=sys.stderr)
        return []


def save_alerts(alerts: List[Dict[str, Any]]) -> bool:
    """
    Save alerts to the alerts file.

    Args:
        alerts: List of alert configurations

    Returns:
        True if successful, False otherwise
    """
    try:
        with open(ALERTS_FILE, "w") as f:
            json.dump({"alerts": alerts, "updated": datetime.now().isoformat()}, f, indent=2)
        return True
    except Exception as e:
        print(f"[error] Failed to save alerts: {e}", file=sys.stderr)
        return False


def add_alert(
    city_key: str,
    min_rating: int = 7,
    notify_slack: bool = True,
    notify_email: bool = False,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Add a new alert configuration.

    Args:
        city_key: City key to monitor
        min_rating: Minimum rating to trigger alert (default 7)
        notify_slack: Whether to send Slack notifications
        notify_email: Whether to send email notifications
        name: Optional name for this alert

    Returns:
        The created alert configuration
    """
    alerts = load_alerts()

    alert = {
        "id": f"alert_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "city_key": city_key,
        "min_rating": min_rating,
        "notify_slack": notify_slack,
        "notify_email": notify_email,
        "name": name or f"{city_key} alert",
        "created": datetime.now().isoformat(),
        "last_triggered": None,
    }

    alerts.append(alert)
    save_alerts(alerts)

    return alert


def remove_alert(alert_id: str) -> bool:
    """
    Remove an alert by ID.

    Args:
        alert_id: ID of the alert to remove

    Returns:
        True if removed, False if not found
    """
    alerts = load_alerts()
    original_len = len(alerts)
    alerts = [a for a in alerts if a.get("id") != alert_id]

    if len(alerts) < original_len:
        save_alerts(alerts)
        return True
    return False


def list_alerts() -> List[Dict[str, Any]]:
    """
    List all configured alerts.

    Returns:
        List of alert configurations
    """
    return load_alerts()


def check_alerts(forecasts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Check forecasts against configured alerts and send notifications.

    Args:
        forecasts: List of forecast dictionaries

    Returns:
        List of triggered alerts
    """
    alerts = load_alerts()
    triggered = []

    # Build lookup by city key
    forecast_by_city = {}
    for f in forecasts:
        city_key = f.get("city_key")
        if city_key:
            forecast_by_city[city_key] = f

    for alert in alerts:
        city_key = alert.get("city_key")
        min_rating = alert.get("min_rating", 7)

        if city_key not in forecast_by_city:
            continue

        forecast = forecast_by_city[city_key]
        rating = forecast.get("rating", 0)

        if rating >= min_rating:
            triggered.append({
                "alert": alert,
                "forecast": forecast,
            })

            # Send notifications
            _send_alert_notifications(alert, forecast)

            # Update last triggered
            alert["last_triggered"] = datetime.now().isoformat()

    # Save updated alerts (with last_triggered times)
    if triggered:
        save_alerts(alerts)

    return triggered


def _send_alert_notifications(alert: Dict[str, Any], forecast: Dict[str, Any]) -> None:
    """
    Send notifications for a triggered alert.

    Args:
        alert: Alert configuration
        forecast: Forecast that triggered the alert
    """
    city = forecast.get("city", "Unknown")
    rating = forecast.get("rating", 0)
    label = forecast.get("label", "Today")
    wind = forecast.get("wind_line", "—")
    waves = forecast.get("waves_line", "—")
    sky = forecast.get("sky_line", "—")

    message = (
        f"🚨 Sailing Alert: {city}\n"
        f"{label}: {rating}/10 (threshold: {alert.get('min_rating')})\n"
        f"Wind: {wind}, Waves: {waves}, Sky: {sky}"
    )

    if alert.get("notify_slack"):
        try:
            post_slack(message)
        except Exception as e:
            print(f"[warn] Failed to send Slack alert: {e}", file=sys.stderr)

    if alert.get("notify_email"):
        try:
            html = f"""
            <h2>🚨 Sailing Alert: {city}</h2>
            <p><strong>{label}:</strong> {rating}/10 (threshold: {alert.get('min_rating')})</p>
            <ul>
                <li>Wind: {wind}</li>
                <li>Waves: {waves}</li>
                <li>Sky: {sky}</li>
            </ul>
            """
            send_email_html(f"Sailing Alert: {city} - {rating}/10", html, message)
        except Exception as e:
            print(f"[warn] Failed to send email alert: {e}", file=sys.stderr)


def format_alerts_list(alerts: List[Dict[str, Any]]) -> str:
    """
    Format alerts list for display.

    Args:
        alerts: List of alert configurations

    Returns:
        Formatted string
    """
    if not alerts:
        return "No alerts configured."

    lines = ["Configured Alerts:", "=" * 40]
    for a in alerts:
        notify = []
        if a.get("notify_slack"):
            notify.append("slack")
        if a.get("notify_email"):
            notify.append("email")
        notify_str = ", ".join(notify) if notify else "none"

        lines.append(
            f"  [{a['id']}] {a['city_key']}: rating >= {a.get('min_rating', 7)} → {notify_str}"
        )
        if a.get("last_triggered"):
            lines.append(f"      Last triggered: {a['last_triggered']}")

    return "\n".join(lines)

