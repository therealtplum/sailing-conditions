"""Watch rules — the "tell me when it's good" half of the tool.

A rule is a standing question ("is Belmont Harbor going to be above 7.5 for
at least three hours in the next three days?") evaluated on a schedule by
cron or a GitHub Action. Two properties matter for something that runs
unattended:

*It must not spam.* Every fired rule is recorded in a small state file, and
a rule will not fire again for the same spot and date until its cooldown
expires. A forecast that wobbles between 7.4 and 7.6 all afternoon produces
one message, not fifty.

*It must not lie by omission.* A rule that could not be evaluated — grid
down, spot renamed — is reported as an error rather than silently counted
as "nothing to report".
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import DayOutlook, Report, Window
from .notify import Notifier, NotifyError
from .profiles import DEFAULT_PROFILE, get_profile
from .service import Forecaster
from .settings import Settings
from .spots import SpotRegistry

log = logging.getLogger(__name__)

DEFAULT_COOLDOWN_HOURS = 20.0


@dataclass(frozen=True, slots=True)
class WatchRule:
    """One standing question about one spot."""

    spot: str
    profile: str = DEFAULT_PROFILE
    min_score: float = 7.0
    min_hours: int = 2
    days: int = 3
    channels: tuple[str, ...] = ("slack",)
    cooldown_hours: float = DEFAULT_COOLDOWN_HOURS
    name: str = ""

    @property
    def key(self) -> str:
        """Stable identifier used for state keys and log lines."""
        return self.name or f"{self.spot}@{self.profile}>={self.min_score:g}"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> WatchRule:
        """Build a rule from a ``[[watch]]`` table in the config file.

        Raises:
            ValueError: if the rule has no spot.
        """
        spot = str(data.get("spot", "")).strip()
        if not spot:
            raise ValueError("watch rule is missing `spot`")
        channels = data.get("channels", ("slack",))
        if isinstance(channels, str):
            channels = [part.strip() for part in channels.split(",") if part.strip()]
        return cls(
            spot=spot,
            profile=str(data.get("profile", DEFAULT_PROFILE)),
            min_score=float(data.get("min_score", 7.0)),
            min_hours=int(data.get("min_hours", 2)),
            days=int(data.get("days", 3)),
            channels=tuple(str(channel) for channel in channels),
            cooldown_hours=float(data.get("cooldown_hours", DEFAULT_COOLDOWN_HOURS)),
            name=str(data.get("name", "")),
        )


def rules_from_settings(settings: Settings) -> list[WatchRule]:
    """Parse every ``[[watch]]`` table in the user's config."""
    return [WatchRule.from_mapping(raw) for raw in settings.watch_rules]


@dataclass
class WatchState:
    """Persisted record of when each rule last fired.

    Deliberately a plain JSON file: it is inspectable, deletable, and does
    not need a daemon or a database to survive a reboot.
    """

    path: Path
    fired: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | str) -> WatchState:
        """Read state from disk, tolerating a missing or corrupt file."""
        path = Path(path)
        try:
            data = json.loads(path.read_text("utf-8"))
            fired = {str(k): str(v) for k, v in (data.get("fired") or {}).items()}
        except (OSError, ValueError):
            fired = {}
        return cls(path=path, fired=fired)

    def save(self) -> None:
        """Persist state, creating parent directories as needed."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"fired": self.fired}, indent=2), encoding="utf-8")
        except OSError as exc:  # pragma: no cover - platform dependent
            log.warning("could not write watch state to %s: %s", self.path, exc)

    @staticmethod
    def state_key(rule: WatchRule, day: dt.date) -> str:
        """Key identifying one rule firing for one forecast date."""
        return f"{rule.key}|{day.isoformat()}"

    def suppressed(self, rule: WatchRule, day: dt.date, now: dt.datetime) -> bool:
        """Whether this rule already fired for this date inside its cooldown."""
        raw = self.fired.get(self.state_key(rule, day))
        if not raw:
            return False
        try:
            last = dt.datetime.fromisoformat(raw)
        except ValueError:
            return False
        if last.tzinfo is None:
            last = last.replace(tzinfo=dt.UTC)
        return (now - last) < dt.timedelta(hours=rule.cooldown_hours)

    def record(self, rule: WatchRule, day: dt.date, now: dt.datetime) -> None:
        """Mark a rule as fired for a date."""
        self.fired[self.state_key(rule, day)] = now.isoformat()

    def prune(self, before: dt.date) -> None:
        """Drop entries for dates that are already in the past."""
        self.fired = {
            key: value
            for key, value in self.fired.items()
            if key.rsplit("|", 1)[-1] >= before.isoformat()
        }


@dataclass(frozen=True, slots=True)
class WatchHit:
    """A rule that matched, and the evidence for it."""

    rule: WatchRule
    report: Report
    day: DayOutlook
    window: Window

    def headline(self) -> str:
        """Message subject line."""
        return (
            f"⛵ {self.report.spot.name}: {self.day.score:.1f}/10 "
            f"{self.day.date:%a %d %b} — {self.window.describe()}"
        )


def evaluate(rule: WatchRule, report: Report) -> WatchHit | None:
    """Return the first day that satisfies the rule, if any.

    "First" rather than "best" on purpose: a good day tomorrow is more
    actionable than a slightly better one next week.
    """
    for day in report.days:
        for window in day.windows:
            if window.length_hours >= rule.min_hours and window.mean_score >= rule.min_score:
                return WatchHit(rule=rule, report=report, day=day, window=window)
    return None


def run_watch(
    rules: Sequence[WatchRule],
    *,
    forecaster: Forecaster,
    registry: SpotRegistry,
    settings: Settings,
    state: WatchState,
    notifiers: Mapping[str, Iterable[Notifier]] | None = None,
    now: dt.datetime | None = None,
    dry_run: bool = False,
) -> tuple[list[WatchHit], list[str]]:
    """Evaluate every rule and notify on the ones that fire.

    Args:
        rules: The rules to evaluate.
        forecaster: Source of reports.
        registry: Spot lookup, including user-defined spots.
        settings: Used to build notifiers when ``notifiers`` is not given.
        state: Cooldown bookkeeping; updated in place and saved unless dry.
        notifiers: Optional pre-built channel map, for tests.
        now: Injectable clock.
        dry_run: Evaluate and report, but neither notify nor persist.

    Returns:
        ``(hits, errors)`` — hits that were (or would have been) notified,
        and one human-readable string per rule that could not be evaluated.
    """
    from .notify import build_notifiers  # deferred: keeps import graph acyclic

    now = now or dt.datetime.now(dt.UTC)
    hits: list[WatchHit] = []
    errors: list[str] = []

    for rule in rules:
        try:
            spot = registry.get(rule.spot)
            profile = get_profile(rule.profile, settings.user_profiles)
            report = forecaster.report(
                spot,
                profile,
                days=rule.days,
                min_score=rule.min_score,
                min_hours=rule.min_hours,
                now=now,
            )
        except Exception as exc:
            errors.append(f"{rule.key}: {exc}")
            continue

        hit = evaluate(rule, report)
        if hit is None:
            log.info("%s: nothing above %.1f", rule.key, rule.min_score)
            continue
        if state.suppressed(rule, hit.day.date, now):
            log.info("%s: already notified for %s", rule.key, hit.day.date)
            continue

        hits.append(hit)
        if dry_run:
            continue

        channels = notifiers.get(rule.key) if notifiers else None
        targets = list(channels) if channels is not None else build_notifiers(settings, rule.channels)
        if not targets:
            errors.append(f"{rule.key}: no configured channel among {', '.join(rule.channels)}")
            continue

        delivered = False
        for notifier in targets:
            try:
                notifier.send(hit.headline(), [hit.report])
                delivered = True
            except NotifyError as exc:
                errors.append(f"{rule.key}: {notifier.name} delivery failed: {exc}")
        if delivered:
            state.record(rule, hit.day.date, now)

    if not dry_run:
        state.prune(now.date() - dt.timedelta(days=1))
        state.save()
    return hits, errors
