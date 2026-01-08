# Sailing Conditions

⛵ A lightweight Python package for quick sailing condition summaries across multiple cities.

## Features

- Pulls forecasts from NWS (grid + marine)
- Simple 1–10 sailing rating based on wind, waves, and weather
- **JSON output** for integrations and automation
- **7-day forecasts** for planning ahead
- **Temperature display** in both Fahrenheit and Celsius
- **Verbose mode** with detailed rating breakdowns
- **Best sailing window** finder (optimal hours)
- **Sunrise/sunset times** for each city
- **Alert notifications** for favorable conditions
- Outputs to Slack or email
- Extensible city list (20+ cities supported)
- Retry logic with exponential backoff for network requests
- Cross-platform support
- Comprehensive test suite (225 tests)

## Requirements

- Python 3.10+
- `requests` library

## Installation

```bash
# Using uv (recommended)
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Or using pip
pip install -e ".[dev]"
```

## Usage

### Basic Examples

```bash
# Today's forecast for Chicago, send to Slack
python -m sailing_conditions.cli --today --only chicago --slack

# Tomorrow's forecast for multiple cities, send to email
python -m sailing_conditions.cli --tomorrow --only miami,nyc,sf --email

# Weekend forecast for all cities, send to both Slack and email
python -m sailing_conditions.cli --weekend --all-cities --all-delivery

# Use legacy flags
python -m sailing_conditions.cli --today --chicago --nyc --slack

# Use city flags directly
python -m sailing_conditions.cli --today --miami --boston
```

### New Features

```bash
# JSON output for automation
python -m sailing_conditions.cli --today --only chicago --format json

# 7-day forecast
python -m sailing_conditions.cli --week --only chicago

# Verbose mode with rating breakdown
python -m sailing_conditions.cli --today --only chicago --verbose

# JSON + week forecast
python -m sailing_conditions.cli --week --only chicago --format json
```

### Alert Notifications

Set up proactive alerts for favorable sailing conditions:

```bash
# Add an alert (notify when rating >= 7)
python -m sailing_conditions.cli --alert-add --city chicago --min-rating 7 --slack

# Add an alert with email notification
python -m sailing_conditions.cli --alert-add --city miami --min-rating 8 --email

# List all alerts
python -m sailing_conditions.cli --alert-list

# Check alerts against current conditions
python -m sailing_conditions.cli --alert-check --only chicago

# Remove an alert
python -m sailing_conditions.cli --alert-remove alert_20250107143022
```

### Programmatic Usage

```python
from sailing_conditions import (
    chicago_forecast,
    marine_city_forecast,
    grid_city_forecast,
    week_forecast,
    find_best_sailing_window,
    compute_rating_breakdown,
    parse_wind,
    CITIES,
    # Alerts
    add_alert,
    check_alerts,
    list_alerts,
)

# Get Chicago forecast with detailed breakdown
forecast = chicago_forecast("TODAY", include_details=True)
print(f"Rating: {forecast['rating']}/10")
print(f"Wind: {forecast['wind_line']}")
print(f"Waves: {forecast['waves_line']}")
print(f"Temperature: {forecast.get('temp_f')}°F")
print(f"Sunrise: {forecast['sun']['sunrise']}")

# Rating breakdown
if forecast.get('rating_breakdown'):
    rb = forecast['rating_breakdown']
    print(f"Base: {rb['base']}, Wind adj: {rb['wind_adj']}, Final: {rb['final']}")

# Get 7-day forecast
week = week_forecast("chicago")
for day in week:
    print(f"{day['label']}: {day['rating']}/10")

# Find best sailing window for today
best = find_best_sailing_window("chicago")
if best:
    print(f"Best window: {best['start_time']}–{best['end_time']} (avg {best['avg_rating']}/10)")

# Set up alerts programmatically
alert = add_alert("miami", min_rating=8, notify_slack=True)
triggered = check_alerts([forecast])
```

### Command-Line Options

**Day Selection (mutually exclusive):**
- `--today` - Use today's forecast (default)
- `--tomorrow` - Use tomorrow's forecast
- `--weekend` - Use Saturday & Sunday
- `--week` - Show 7-day forecast

**Output Format:**
- `--format text` - Human-readable text (default)
- `--format json` - JSON output for automation
- `--verbose`, `-v` - Show detailed rating breakdown

**City Selection:**
- `--only CITY1,CITY2` - Comma-separated list of city keys
- `--all-cities` - Include every city in the registry
- `--chicago`, `--nyc`, `--philly`, `--kc`, `--slc` - Legacy flags
- `--CITYKEY` - Direct city flags (e.g., `--miami`, `--boston`)

**Delivery:**
- `--email` - Send to email
- `--slack` - Send to Slack
- `--all-delivery` - Send to both email and Slack
- `--all` - Alias for both `--all-cities` and `--all-delivery`
- `--no-send` - Don't send, just print output

**Alert Management:**
- `--alert-add` - Add a new alert
- `--alert-remove ID` - Remove an alert by ID
- `--alert-list` - List all configured alerts
- `--alert-check` - Check alerts against current conditions
- `--city KEY` - City key for alert (with --alert-add)
- `--min-rating N` - Minimum rating to trigger alert (default: 7)

**Default Behavior:**
- If no delivery method specified, sends to both email and Slack
- If no cities specified, uses default cities: chicago, philly, kc, slc, nyc

## Configuration

### Environment Variables

**Email (SMTP):**
- `SMTP_HOST` - SMTP server hostname
- `SMTP_PORT` - SMTP port (465 for SSL, 587 for STARTTLS)
- `SMTP_USER` - SMTP username (optional)
- `SMTP_PASS` - SMTP password (optional)
- `EMAIL_FROM` - Sender email address
- `EMAIL_TO` - Recipient email(s), comma or semicolon separated

**Slack:**
- `SLACK_WEBHOOK_URL` - Incoming webhook URL (preferred), OR
- `SLACK_BOT_TOKEN` - Bot token
- `SLACK_CHANNEL` - Channel ID or name

**Other:**
- `SUGGESTION_MODE=stable` - Use deterministic suggestions (for testing)
- `SAILING_CONDITIONS_CONTACT` - Contact email for NWS API User-Agent header
- `SAILING_CONDITIONS_ALERTS_FILE` - Custom path for alerts storage (default: ~/.sailing-conditions-alerts.json)

### Supported Cities

The package supports 20+ cities including:
- **Sailing cities:** Chicago, NYC, Miami, Fort Lauderdale, Tampa Bay, LA, San Diego, San Francisco, Seattle, Boston, Newport, Annapolis, Portland (ME), Charleston, New Orleans, Cleveland, Milwaukee, Austin
- **Non-sailing cities:** Philadelphia, Kansas City, Salt Lake City, Minneapolis

See `sailing_conditions/cities.py` for the full list and to add more.

## Rating System

The 1–10 rating is computed based on:
- **Wind speed:** Optimal range is 9–18 knots
- **Wave height:** Optimal range is 1–3 feet
- **Weather:** Sunny/clear conditions get a bonus; storms/rain get penalties

### Rating Breakdown (Verbose Mode)

Use `--verbose` to see how the rating is calculated:

```
Rating Breakdown:
  Base score: 10
  Wind: -1 (light (8kt < 9kt))
  Waves: 0 (optimal (3ft ≤ 3ft))
  Sky: +1 (sunny/clear (+1))
  Raw score: 10 → Final: 10
```

## JSON Output

The `--format json` option outputs structured data:

```json
{
  "forecasts": [
    {
      "city": "Chicago",
      "city_key": "chicago",
      "label": "Today",
      "date": "2025-01-07",
      "rating": 8,
      "wind": "N 10–15 kt",
      "waves": "2–3 ft",
      "sky": "Sunny",
      "sailing": true,
      "temperature": {"fahrenheit": 75, "celsius": 24},
      "wind_kt": {"low": 10, "high": 15},
      "waves_ft": {"low": 2.0, "high": 3.0},
      "sun": {"sunrise": "6:30am", "sunset": "8:15pm", "daylight_hours": 13.75},
      "best_window": {"start_time": "10am", "end_time": "2pm", "avg_rating": 8.5}
    }
  ],
  "count": 1
}
```

## Development

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=sailing_conditions
```

### Project Structure

```
sailing_conditions/
├── __init__.py      # Public API exports
├── alerts.py        # Alert notification system
├── cli.py           # Command-line interface
├── cities.py        # City registry
├── config.py        # Configuration constants
├── emoji.py         # Weather emoji selection
├── fetchers.py      # Network requests (NWS, NDBC, sun times)
├── forecast.py      # Forecast generation logic
├── formatters.py    # Output formatting (Slack, HTML, JSON, verbose)
├── parsers.py       # Text parsing (wind, waves, sky, rating breakdown)
└── senders.py       # Email and Slack delivery

tests/
├── test_cities.py
├── test_cli.py
├── test_config.py
├── test_emoji.py
├── test_fetchers.py
├── test_forecast.py
├── test_formatters.py
├── test_new_features.py  # JSON, week, verbose, alerts tests
├── test_parsers.py
└── test_senders.py
```

## License

MIT License - see [LICENSE](LICENSE) file.
