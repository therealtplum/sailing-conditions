"""Command-line interface.

The CLI is deliberately thin: it parses arguments, builds a context, calls
into :mod:`sailing_conditions.service`, and hands the result to a renderer.
Every command takes its dependencies from a :class:`Context` that tests can
construct with a fixture-backed fetcher, which is why the end-to-end tests
run the real ``main()`` with no network.

Exit codes: ``0`` success, ``1`` runtime failure, ``2`` bad usage.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .models import Report, Spot
from .profiles import BUILTIN_PROFILES, BoatProfile, get_profile
from .render import jsonout, render_report, render_summary
from .service import Forecaster, build_forecaster
from .settings import PACKAGE_VERSION, ConfigError, Settings
from .sources.http import Fetcher
from .spots import SpotRegistry, UnknownSpot
from .watch import WatchState, rules_from_settings, run_watch

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

MAX_DAYS = 7


@dataclass(frozen=True, slots=True)
class Context:
    """Everything a command needs, assembled once in :func:`main`."""

    settings: Settings
    registry: SpotRegistry
    forecaster: Forecaster
    console: Console
    args: argparse.Namespace

    def profile(self) -> BoatProfile:
        """The boat profile selected on the command line or in config."""
        return get_profile(self.args.profile or self.settings.profile, self.settings.user_profiles)

    def spots(self) -> list[Spot]:
        """Resolve the requested spots, falling back to the configured default."""
        keys = list(self.args.spots) or list(self.settings.spots)
        return self.registry.resolve(keys)

    def reports(self, *, days: int) -> list[Report]:
        """Build reports for the selected spots."""
        return self.forecaster.reports(
            self.spots(),
            self.profile(),
            days=days,
            min_score=self.args.min_score if self.args.min_score is not None else self.settings.min_score,
            min_hours=self.settings.min_hours,
            live=not self.args.no_live,
        )


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser for every subcommand."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("spots", nargs="*", help="spot keys (default: from config, else chicago)")
    common.add_argument("-p", "--profile", help=f"boat profile ({', '.join(BUILTIN_PROFILES)})")
    common.add_argument("--min-score", type=float, help="score an hour must clear to join a window")
    common.add_argument("--json", action="store_true", help="emit JSON instead of a rendered report")
    common.add_argument("--compact", action="store_true", help="with --json, omit the hour-by-hour detail")
    common.add_argument("--explain", action="store_true", help="show the factor arithmetic behind the score")
    common.add_argument("--no-live", action="store_true", help="skip buoy observations")
    common.add_argument("--no-cache", action="store_true", help="bypass the on-disk HTTP cache")
    common.add_argument("--no-color", action="store_true", help="disable color output")
    common.add_argument("-v", "--verbose", action="store_true", help="log what the fetcher is doing")

    parser = argparse.ArgumentParser(
        prog="sail",
        description="Is it worth going sailing? Hourly NWS data, scored for your boat.",
        epilog=(
            "examples:\n"
            "  sail now chicago\n"
            "  sail week sfbay --profile dinghy --explain\n"
            "  sail compare chicago milwaukee cleveland --days 3\n"
            "  sail watch --dry-run\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"sailing-conditions {PACKAGE_VERSION}")
    subs = parser.add_subparsers(dest="command")

    now = subs.add_parser("now", parents=[common], help="today's window, plus live buoy conditions")
    now.set_defaults(func=cmd_now, days=1)

    plan = subs.add_parser("plan", parents=[common], help="the next few days at one or more spots")
    plan.add_argument("-d", "--days", type=int, default=3, help="days to include (1-7, default 3)")
    plan.set_defaults(func=cmd_plan)

    week = subs.add_parser("week", parents=[common], help="the full seven-day outlook")
    week.set_defaults(func=cmd_plan, days=7)

    compare = subs.add_parser("compare", parents=[common], help="rank several spots against each other")
    compare.add_argument("-d", "--days", type=int, default=3, help="days to consider (1-7, default 3)")
    compare.set_defaults(func=cmd_compare)

    spots = subs.add_parser("spots", help="list known spots")
    spots.add_argument("--tag", help="only spots carrying this tag")
    spots.add_argument("--json", action="store_true", help="emit JSON")
    spots.set_defaults(func=cmd_spots)

    profiles = subs.add_parser("profiles", help="list boat profiles and their wind bands")
    profiles.set_defaults(func=cmd_profiles)

    watch = subs.add_parser("watch", help="evaluate the watch rules in your config and notify")
    watch.add_argument("--dry-run", action="store_true", help="evaluate and print, but do not send or persist")
    watch.add_argument("--no-cache", action="store_true", help="bypass the on-disk HTTP cache")
    watch.add_argument("-v", "--verbose", action="store_true", help="log what the fetcher is doing")
    watch.set_defaults(func=cmd_watch)

    return parser


def cmd_now(ctx: Context) -> int:
    """Today only, with live observations if the spot has a buoy."""
    return _emit(ctx, ctx.reports(days=1))


def cmd_plan(ctx: Context) -> int:
    """A multi-day outlook per spot."""
    days = max(1, min(MAX_DAYS, int(getattr(ctx.args, "days", 3))))
    return _emit(ctx, ctx.reports(days=days))


def cmd_compare(ctx: Context) -> int:
    """A leaderboard across spots rather than a panel per spot."""
    days = max(1, min(MAX_DAYS, int(getattr(ctx.args, "days", 3))))
    reports = ctx.reports(days=days)
    if ctx.args.json:
        ctx.console.print_json(jsonout.dumps(reports, hourly=not ctx.args.compact))
        return EXIT_OK
    render_summary(reports, ctx.console)
    _print_notes(ctx, reports)
    return EXIT_OK


def cmd_spots(ctx: Context) -> int:
    """List the spot registry."""
    spots = ctx.registry.tagged(ctx.args.tag) if ctx.args.tag else list(ctx.registry)
    if getattr(ctx.args, "json", False):
        ctx.console.print_json(
            json.dumps(
                [
                    {
                        "key": s.key,
                        "name": s.name,
                        "region": s.region,
                        "lat": s.lat,
                        "lon": s.lon,
                        "buoy": s.buoy,
                        "tags": list(s.tags),
                    }
                    for s in spots
                ]
            )
        )
        return EXIT_OK

    table = Table(title="Sailing spots", box=None, title_style="bold", title_justify="left", header_style="grey62")
    table.add_column("key", style="bold cyan")
    table.add_column("name")
    table.add_column("region", style="grey62")
    table.add_column("buoy", style="grey62")
    table.add_column("notes", style="italic grey54")
    for spot in spots:
        table.add_row(spot.key, spot.name, spot.region, spot.buoy or "—", spot.blurb)
    ctx.console.print(table)
    ctx.console.print(
        Text("\nAdd your own under [spots] in ~/.config/sailing-conditions/config.toml", style="grey54")
    )
    return EXIT_OK


def cmd_profiles(ctx: Context) -> int:
    """List boat profiles and the wind bands that define them."""
    table = Table(title="Boat profiles", box=None, title_style="bold", title_justify="left", header_style="grey62")
    table.add_column("key", style="bold cyan")
    table.add_column("wind (min–ideal–max)")
    table.add_column("seas ok / max")
    table.add_column("what it assumes", style="grey62")
    profiles = {**BUILTIN_PROFILES, **ctx.settings.user_profiles}
    for key, profile in profiles.items():
        table.add_row(
            key,
            profile.wind.describe(),
            f"{profile.wave_ok_ft:g} / {profile.wave_max_ft:g} ft",
            profile.summary,
        )
    ctx.console.print(table)
    return EXIT_OK


def cmd_watch(ctx: Context) -> int:
    """Evaluate configured watch rules and notify on matches."""
    rules = rules_from_settings(ctx.settings)
    if not rules:
        ctx.console.print(
            Text(
                "No watch rules configured. Add a [[watch]] block to "
                f"{ctx.settings.config_path or '~/.config/sailing-conditions/config.toml'}",
                style="yellow",
            )
        )
        return EXIT_OK

    hits, errors = run_watch(
        rules,
        forecaster=ctx.forecaster,
        registry=ctx.registry,
        settings=ctx.settings,
        state=WatchState.load(ctx.settings.state_path),
        dry_run=ctx.args.dry_run,
    )

    for hit in hits:
        prefix = "would notify" if ctx.args.dry_run else "notified"
        ctx.console.print(Text(f"{prefix}: {hit.headline()}", style=hit.day.verdict.color))
    if not hits:
        ctx.console.print(Text(f"Checked {len(rules)} rule(s); nothing worth a message.", style="grey62"))
    for error in errors:
        ctx.console.print(Text(f"error: {error}", style="red"), style="red")
    return EXIT_ERROR if errors else EXIT_OK


def _emit(ctx: Context, reports: list[Report]) -> int:
    if ctx.args.json:
        ctx.console.print_json(jsonout.dumps(reports, hourly=not ctx.args.compact))
        return EXIT_OK
    for report in reports:
        render_report(report, ctx.console, explain=ctx.args.explain)
    return EXIT_OK


def _print_notes(ctx: Context, reports: list[Report]) -> None:
    for report in reports:
        for note in report.notes:
            ctx.console.print(Text(f"  {report.spot.key}: {note}", style="grey54"))


def main(
    argv: Sequence[str] | None = None,
    *,
    fetcher: Fetcher | None = None,
    console: Console | None = None,
    settings: Settings | None = None,
) -> int:
    """Entry point. Returns a process exit code rather than calling ``sys.exit``.

    Args:
        argv: Command-line arguments, defaulting to ``sys.argv[1:]``.
        fetcher: Injected HTTP layer — the seam the test suite uses.
        console: Injected Rich console, for capturing output.
        settings: Injected settings, bypassing the config file.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return EXIT_USAGE

    logging.basicConfig(
        level=logging.INFO if getattr(args, "verbose", False) else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    try:
        resolved = settings or Settings.load()
    except ConfigError as exc:
        (console or Console(stderr=True)).print(Text(f"config error: {exc}", style="bold red"))
        return EXIT_ERROR

    out = console or Console(no_color=getattr(args, "no_color", False))
    registry = SpotRegistry().merged(resolved.user_spots)
    ctx = Context(
        settings=resolved,
        registry=registry,
        forecaster=build_forecaster(
            resolved,
            fetcher=fetcher,
            use_cache=not getattr(args, "no_cache", False),
            live=not getattr(args, "no_live", False),
        ),
        console=out,
        args=args,
    )

    try:
        return int(args.func(ctx))
    except UnknownSpot as exc:
        out.print(Text(f"error: {exc}", style="bold red"))
        return EXIT_USAGE
    except KeyError as exc:
        out.print(Text(f"error: {exc.args[0] if exc.args else exc}", style="bold red"))
        return EXIT_USAGE
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        out.print("\ninterrupted")
        return EXIT_ERROR
    except Exception as exc:
        out.print(Text(f"error: {exc}", style="bold red"))
        if getattr(args, "verbose", False):
            out.print_exception()
        return EXIT_ERROR


def run() -> None:
    """Console-script shim that translates the return code into an exit."""
    raise SystemExit(main())


if __name__ == "__main__":
    run()
