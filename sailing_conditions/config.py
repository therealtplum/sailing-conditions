"""Configuration constants for sailing-conditions package."""
from __future__ import annotations

import os

# User-Agent for NWS API requests
# Can be overridden via SAILING_CONDITIONS_CONTACT env var
_contact = os.environ.get("SAILING_CONDITIONS_CONTACT", "sailing-conditions-user")
NWS_UA = f"SailingConditions/1.0 (contact: {_contact})"

TGFTP_ROOT = "https://tgftp.nws.noaa.gov/data/forecasts"

# Chicago nearshore LMZ set + CHII2 obs
CHICAGO_NEARSHORE = [
    "marine/near_shore/lm/lmz740.txt",
    "marine/near_shore/lm/lmz741.txt",
    "marine/near_shore/lm/lmz742.txt",
    "marine/near_shore/lm/lmz743.txt",
    "marine/near_shore/lm/lmz744.txt",
    "marine/near_shore/lm/lmz745.txt",
]
NDBC_STATION = "CHII2"  # Harrison-Dever Crib
NDBC_REALTIME = "https://www.ndbc.noaa.gov/data/realtime2/{station}.txt"

DEFAULT_KEYS = ["chicago", "philly", "kc", "slc", "nyc"]

# --------------------
# Unit Conversion Constants
# --------------------
MPH_TO_KNOTS = 0.868976  # multiply mph by this to get knots
MS_TO_KNOTS = 1.943844   # multiply m/s by this to get knots

# --------------------
# Weather Keywords
# --------------------
# Words indicating severe/hazardous conditions
SEVERE_WORDS = frozenset({
    "hazard", "warning", "gale", "storm", "hurricane", "hvy freezing spray"
})

# Words indicating rainy conditions
RAINY_WORDS = frozenset({
    "rain", "showers", "thunder", "storm", "t-storm", "drizzle"
})

# --------------------
# Rating Algorithm Constants
# --------------------
# Wind: optimal range is 9-18 knots
WIND_OPTIMAL_LOW = 9
WIND_OPTIMAL_HIGH = 18
WIND_DANGEROUS_HIGH = 28
WIND_VERY_HIGH = 23

# Waves: optimal range is 1-3 feet
WAVE_OPTIMAL_HIGH = 3.0
WAVE_DANGEROUS_HIGH = 5.0
WAVE_VERY_HIGH = 4.0
