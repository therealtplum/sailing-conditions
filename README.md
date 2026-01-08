# Sailing Conditions

⛵ A lightweight Python package for quick sailing condition summaries across multiple cities.

## Features

- Pulls forecasts from NWS (grid + marine)
- Simple 1–10 sailing rating based on wind, waves, and weather
- Outputs to Slack or email
- Extensible city list (20+ cities supported)
- Retry logic with exponential backoff for network requests
- Cross-platform support
- Comprehensive test suite (193 tests)

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

### Programmatic Usage

```python
from sailing_conditions import (
    chicago_forecast,
    marine_city_forecast,
    grid_city_forecast,
    parse_wind,
    compute_rating,
    CITIES,
)

# Get Chicago forecast
forecast = chicago_forecast("TODAY")
print(f"Rating: {forecast['rating']}/10")
print(f"Wind: {forecast['wind_line']}")
print(f"Waves: {forecast['waves_line']}")

# Get forecast for any marine city
miami = marine_city_forecast("miami", "TOMORROW")

# Parse wind from text
direction, speed_range = parse_wind("N 10 to 15 kt")
```

### Command-Line Options

**Day Selection (mutually exclusive):**
- `--today` - Use today's forecast (default)
- `--tomorrow` - Use tomorrow's forecast
- `--weekend` - Use Saturday & Sunday

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
├── cli.py           # Command-line interface
├── cities.py        # City registry
├── config.py        # Configuration constants
├── emoji.py         # Weather emoji selection
├── fetchers.py      # Network requests (NWS, NDBC)
├── forecast.py      # Forecast generation logic
├── formatters.py    # Output formatting (Slack, HTML)
├── parsers.py       # Text parsing (wind, waves, sky)
└── senders.py       # Email and Slack delivery

tests/
├── test_cities.py
├── test_cli.py
├── test_config.py
├── test_emoji.py
├── test_fetchers.py
├── test_forecast.py
├── test_formatters.py
├── test_parsers.py
└── test_senders.py
```

## License

MIT License - see [LICENSE](LICENSE) file.
