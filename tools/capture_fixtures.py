#!/usr/bin/env python3
"""Refresh the recorded API payloads in ``tests/fixtures``.

The test suite runs entirely offline against these files. When NWS changes
a payload shape, re-record rather than hand-editing::

    python tools/capture_fixtures.py --contact you@example.com

Grid payloads are trimmed to the elements this project reads and to the
first two days of values, which keeps the fixtures reviewable in a diff
instead of being 250 KB of noise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import requests

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

GRID_ELEMENTS = (
    "windSpeed",
    "windGust",
    "windDirection",
    "waveHeight",
    "temperature",
    "apparentTemperature",
    "probabilityOfPrecipitation",
    "probabilityOfThunder",
    "skyCover",
    "weather",
)

MAX_VALUES = 30


def get(url: str, contact: str) -> requests.Response:
    """Fetch a URL with the polite User-Agent the NWS asks for."""
    return requests.get(url, timeout=30, headers={"User-Agent": f"sailing-conditions/fixtures ({contact})"})


def trim_grid(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only the elements the client reads, and only the first values."""
    props = payload["properties"]
    kept = {
        key: {**props[key], "values": props[key].get("values", [])[:MAX_VALUES]}
        for key in GRID_ELEMENTS
        if isinstance(props.get(key), dict)
    }
    meta = {k: props[k] for k in ("validTimes", "updateTime", "gridId", "gridX", "gridY") if k in props}
    return {"properties": {**meta, **kept}}


def main() -> int:
    """Record every fixture the test suite needs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contact", required=True, help="contact address for the NWS User-Agent")
    parser.add_argument("--lat", type=float, default=41.939)
    parser.add_argument("--lon", type=float, default=-87.633)
    parser.add_argument("--buoy", default="CHII2")
    args = parser.parse_args()

    FIXTURES.mkdir(parents=True, exist_ok=True)

    point = get(f"https://api.weather.gov/points/{args.lat:.4f},{args.lon:.4f}", args.contact).json()
    (FIXTURES / "points_chicago.json").write_text(json.dumps(point, indent=1))

    grid_url = point["properties"]["forecastGridData"]
    grid = get(grid_url, args.contact).json()
    (FIXTURES / "grid_chicago.json").write_text(json.dumps(trim_grid(grid), indent=1))

    alerts = get(f"https://api.weather.gov/alerts/active?point={args.lat:.4f},{args.lon:.4f}", args.contact).json()
    (FIXTURES / "alerts_active.json").write_text(json.dumps({"features": alerts.get("features", [])}, indent=1))

    buoy = get(f"https://www.ndbc.noaa.gov/data/realtime2/{args.buoy}.txt", args.contact).text
    (FIXTURES / "ndbc_chii2.txt").write_text("\n".join(buoy.splitlines()[:14]) + "\n")

    print(f"wrote fixtures to {FIXTURES}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
