"""Network fetchers for NWS and NDBC data."""
from __future__ import annotations

import datetime as dt
import sys
import time
from typing import List, Optional

import requests

from .config import MS_TO_KNOTS, NDBC_REALTIME, NWS_UA, TGFTP_ROOT


def http_get(
    url: str,
    timeout: int = 20,
    max_retries: int = 3,
    backoff: float = 1.0,
) -> requests.Response:
    """
    Make an HTTP GET request with retry logic.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds
        max_retries: Maximum number of retry attempts
        backoff: Initial backoff delay in seconds (doubles on each retry)

    Returns:
        Response object

    Raises:
        requests.RequestException: If all retries fail
    """
    last_exception: Optional[requests.RequestException] = None
    for attempt in range(max_retries):
        try:
            return requests.get(
                url,
                timeout=timeout,
                headers={"User-Agent": NWS_UA},
                allow_redirects=True,
            )
        except requests.RequestException as e:
            last_exception = e
            if attempt < max_retries - 1:
                wait_time = backoff * (2**attempt)
                print(
                    f"[warn] HTTP request failed (attempt {attempt + 1}/{max_retries}): {e}. "
                    f"Retrying in {wait_time:.1f}s...",
                    file=sys.stderr,
                )
                time.sleep(wait_time)
            else:
                print(f"[warn] HTTP request failed after {max_retries} attempts: {e}", file=sys.stderr)

    if last_exception is not None:
        raise last_exception
    raise requests.RequestException("HTTP request failed with no exception captured")


def fetch_tgftp_text(rel_path: str) -> Optional[str]:
    """
    Resilient TGFTP fetch: try with and without trailing slash.

    Args:
        rel_path: Relative path to the TGFTP resource

    Returns:
        Text content if successful, None otherwise
    """
    base = f"{TGFTP_ROOT}/{rel_path.lstrip('/')}"
    try_order = [base, base.rstrip("/"), base.rstrip("/") + "/"]
    seen: set[str] = set()
    for url in try_order:
        if url in seen:
            continue
        seen.add(url)
        try:
            r = http_get(url, timeout=15, max_retries=2)
            if r.status_code == 200 and r.text.strip():
                return r.text
        except Exception as e:
            short = url.replace(TGFTP_ROOT + "/", "")
            print(f"[warn] TGFTP fetch failed {short}: {e}", file=sys.stderr)
    return None


def fetch_city_marine_text(zones: List[str]) -> Optional[str]:
    """
    Fetch marine forecast text for multiple zones and combine them.

    Args:
        zones: List of relative paths to marine zone forecast files

    Returns:
        Combined text from all zones, or None if no zones succeeded
    """
    buf = []
    for z in zones:
        t = fetch_tgftp_text(z)
        if t:
            buf.append(f"\n\n===== {z.upper()} =====\n{t.strip()}\n")
    return "\n".join(buf).strip() if buf else None


def fetch_grid_periods(lat: float, lon: float) -> Optional[List[dict]]:
    """
    Fetch NWS gridpoint forecast periods for a given location.

    Args:
        lat: Latitude
        lon: Longitude

    Returns:
        List of forecast periods, or None if fetch fails
    """
    try:
        # Validate coordinates
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            print(f"[warn] Invalid coordinates: lat={lat}, lon={lon}", file=sys.stderr)
            return None

        p = http_get(f"https://api.weather.gov/points/{lat},{lon}", timeout=15, max_retries=2)
        p.raise_for_status()
        point_data = p.json()

        if "properties" not in point_data or "forecast" not in point_data["properties"]:
            print("[warn] Invalid gridpoint response: missing forecast URL", file=sys.stderr)
            return None

        fc_url = point_data["properties"]["forecast"]
        f = http_get(fc_url, timeout=15, max_retries=2)
        f.raise_for_status()
        forecast_data = f.json()

        if "properties" not in forecast_data or "periods" not in forecast_data["properties"]:
            print("[warn] Invalid forecast response: missing periods", file=sys.stderr)
            return None

        return forecast_data["properties"]["periods"]
    except requests.RequestException as e:
        print(f"[warn] Gridpoint fetch failed: {e}", file=sys.stderr)
        return None
    except (KeyError, ValueError) as e:
        print(f"[warn] Gridpoint data parsing failed: {e}", file=sys.stderr)
        return None


def grid_pick_day(periods: Optional[List[dict]], label: str) -> Optional[dict]:
    """
    Pick the most appropriate NWS grid 'forecast' period for a given label.

    Strategy:
    - Resolve the target calendar date from the label ("TODAY", "TOMORROW", weekday names).
    - Prefer periods whose startTime.date() == target_date.
    - For 'today-ish' labels, prefer daytime-ish names ("Today", "This Afternoon", etc.).
    - Otherwise, return the first period matching the date.

    Args:
        periods: List of forecast period dictionaries
        label: Day label to match (e.g., "TODAY", "TOMORROW", "SATURDAY")

    Returns:
        Matching period dictionary, or None if no match found
    """
    if not periods:
        return None

    label_up = (label or "").strip().upper()
    now = dt.datetime.now().astimezone()
    today = now.date()

    # Resolve target date from label
    if label_up in ("REST OF TODAY", "TODAY"):
        target_date = today
        todayish = True
    elif label_up == "TOMORROW":
        target_date = today + dt.timedelta(days=1)
        todayish = False
    else:
        # Weekday name like "SATURDAY" / "SUNDAY" etc.
        weekdays = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
        if label_up in weekdays:
            target_wd = weekdays.index(label_up)
            # find next date with that weekday (including today if it matches)
            delta = (target_wd - today.weekday()) % 7
            target_date = today + dt.timedelta(days=delta)
            todayish = False
        else:
            # Fallback: assume today
            target_date = today
            todayish = True

    # Parse the period dates and filter to the target date
    def _pdate(p: dict) -> Optional[dt.date]:
        # ISO8601 like "2025-08-15T18:00:00-05:00"
        try:
            return dt.datetime.fromisoformat(p.get("startTime", "")).astimezone().date()
        except Exception:
            return None

    same_day = [p for p in periods if _pdate(p) == target_date]
    if not same_day:
        return None

    # For today-ish, prefer explicit dayparts commonly used by NWS
    if todayish:
        name_pref_order = ["today", "this afternoon", "this morning", "this evening"]
        # try to find first matching preferred name
        for cand in name_pref_order:
            for p in same_day:
                nm = (p.get("name") or "").strip().lower()
                if cand == "today" and nm == "today":
                    return p
                if cand != "today" and cand in nm:
                    return p
        # otherwise just take the first for the date
        return same_day[0]

    # Non-today cases: weekend/weekday labels — return the first for that date
    return same_day[0]


def fetch_ndbc_latest(station: str) -> Optional[dict]:
    """
    Fetch latest observations from NDBC (National Data Buoy Center) station.

    Args:
        station: NDBC station identifier (e.g., "CHII2")

    Returns:
        Dictionary with wind direction (deg), wind speed (kt), and wind gust (kt),
        or None if fetch/parsing fails
    """
    try:
        url = NDBC_REALTIME.format(station=station)
        r = http_get(url, timeout=15, max_retries=2)
        r.raise_for_status()

        lines = [ln.strip() for ln in r.text.splitlines() if ln.strip() and not ln.startswith("#")]
        if len(lines) < 2:
            print(f"[warn] NDBC data insufficient: expected at least 2 lines, got {len(lines)}", file=sys.stderr)
            return None

        header = lines[0].split()
        data = lines[1].split()
        idx = {k: i for i, k in enumerate(header)}

        def to_int(s: str) -> Optional[int]:
            try:
                return int(s)
            except (ValueError, TypeError):
                return None

        def to_float(s: str) -> Optional[float]:
            try:
                return float(s)
            except (ValueError, TypeError):
                return None

        # Validate required fields
        required_fields = ["YY", "MM", "DD", "hh", "mm", "WDIR", "WSPD"]
        for k in required_fields:
            if k not in idx:
                print(f"[warn] NDBC data missing required field: {k}", file=sys.stderr)
                return None

        # Parse date/time - handle None values before arithmetic
        yy_raw = to_int(data[idx["YY"]])
        mm_raw = to_int(data[idx["MM"]])
        dd_raw = to_int(data[idx["DD"]])
        hh_raw = to_int(data[idx["hh"]])
        mi_raw = to_int(data[idx["mm"]])

        if None in (yy_raw, mm_raw, dd_raw, hh_raw, mi_raw):
            print("[warn] NDBC date/time parsing failed", file=sys.stderr)
            return None

        # Year handling: NDBC uses 2-digit year, assume 2000s for now
        # This will need updating if data goes past 2099
        year = 2000 + yy_raw if yy_raw < 100 else yy_raw

        # Parse wind data
        wdir = to_int(data[idx["WDIR"]])
        wspd_ms = to_float(data[idx["WSPD"]])
        wgst_ms = to_float(data[idx.get("GST", -1)]) if "GST" in idx else None

        # Convert m/s to knots
        wspd_kt = round(wspd_ms * MS_TO_KNOTS, 1) if wspd_ms is not None else None
        wgst_kt = round(wgst_ms * MS_TO_KNOTS, 1) if wgst_ms is not None else None

        return {"wdir_deg": wdir, "wspd_kt": wspd_kt, "wgst_kt": wgst_kt}
    except requests.RequestException as e:
        print(f"[warn] NDBC fetch failed: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[warn] NDBC parsing failed: {e}", file=sys.stderr)
        return None
