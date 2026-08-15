"""sailing-conditions — hourly sailing forecasts, scored for your boat.

    from sailing_conditions import Settings, SpotRegistry, build_forecaster, get_profile

    forecaster = build_forecaster(Settings.load())
    report = forecaster.report(SpotRegistry().get("chicago"), get_profile("keelboat"), days=2)
    print(report.headline())
    # Belmont Harbor 8.9/10 — SEND IT. Best 12pm–7pm, S 9 kt g13.

The package is layered so each piece can be used on its own:

``sources``  network clients (NWS grid, NDBC buoys) behind one protocol
``models``   frozen domain types, no I/O
``scoring``  the response curves and vetoes that turn conditions into a score
``windows``  window search over scored hours
``service``  wiring: fetch, score, group, assemble
``render``   console, JSON, Slack, HTML — all pure functions of a report
``notify``   delivery channels
``watch``    standing rules, evaluated on a schedule
"""

from .models import (
    DayOutlook,
    Factor,
    Hazard,
    Hour,
    Observation,
    Report,
    Score,
    ScoredHour,
    Spot,
    SunTimes,
    Verdict,
    Veto,
    Window,
)
from .profiles import BUILTIN_PROFILES, BoatProfile, WindBand, get_profile
from .scoring import score_hour, score_hours
from .service import Forecaster, build_fetcher, build_forecaster
from .settings import PACKAGE_VERSION, Settings
from .spots import SpotRegistry, UnknownSpot, builtin_spots
from .sun import sun_times
from .windows import find_windows, sparkline

__version__ = PACKAGE_VERSION

__all__ = [
    "BUILTIN_PROFILES",
    "BoatProfile",
    "DayOutlook",
    "Factor",
    "Forecaster",
    "Hazard",
    "Hour",
    "Observation",
    "Report",
    "Score",
    "ScoredHour",
    "Settings",
    "Spot",
    "SpotRegistry",
    "SunTimes",
    "UnknownSpot",
    "Verdict",
    "Veto",
    "WindBand",
    "Window",
    "__version__",
    "build_fetcher",
    "build_forecaster",
    "builtin_spots",
    "find_windows",
    "get_profile",
    "score_hour",
    "score_hours",
    "sparkline",
    "sun_times",
]
