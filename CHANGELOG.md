# Changelog

All notable changes to this project are documented here. This project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] — 2026-08-15

A rewrite. v1 answered "what is the weather in these cities"; v2 answers "when
today is it worth sailing, for my boat". The CLI, the scoring model and the JSON
schema all changed, hence the major bump.

### Data

- **Replaced prose scraping with the quantitative NWS grid.** v1 parsed sentences
  like `"west wind 10 to 15 mph"` out of text forecast products with regular
  expressions. v2 reads `/gridpoints/{office}/{x},{y}` — typed hourly series with
  declared units, including gusts, wave height, probability of thunder, sky cover
  and apparent temperature, none of which the prose reliably carries.
- **Unit conversion is driven by the API's declared unit of measure**, and an
  unrecognized unit raises instead of silently passing a wrong number downstream.
- **Added NWS active alerts** as a hazard source: Small Craft Advisories, Gale
  Warnings and Special Marine Warnings now affect scores directly.
- **Added a forecast-versus-observation check.** When a nearby NDBC buoy disagrees
  materially with the model, the report says so.
- **Added an HTTP cache** with per-endpoint TTLs, exponential backoff with jitter,
  and `Retry-After` support.

### Scoring

- **New model:** a weighted geometric mean of continuous per-factor response
  curves, plus hard vetoes — replacing v1's additive if-ladder of ±1 and ±2
  adjustments. Any single bad factor now drags the score down, which an
  arithmetic score could not express.
- **Missing data is dropped from the mean** rather than being scored as zero, so
  inland spots with no wave grid are no longer penalized for it.
- **Added boat profiles** (`keelboat`, `dinghy`, `catamaran`, `cruiser`,
  `beginner`, `heavy_air`, `foiler`, plus your own). The rules are shared; the
  constants are data.
- **Every score explains itself** — each factor reports its reading, its
  normalized value and its weight, visible with `--explain` and in JSON.

### Windows

- The unit of the answer is now a **window** — a contiguous run of hours above
  your threshold — rather than a single number for the whole day.
- The day score is the mean of the best three daylight hours, so one dead morning
  does not erase a good afternoon and one flukey hour does not carry the day.

### Fixed

- **Sunrise and sunset were wrong everywhere.** v1 computed UTC minutes and
  reported them as local time, with no timezone conversion at all, on top of a
  simplified formula with a 2-4 minute bias. v2 implements NOAA's algorithm and
  localizes through the IANA zone reported by the NWS point metadata; results are
  verified to within 90 seconds against reference implementations.
- Day-boundary and DST handling: all timestamps are timezone-aware end to end.
- Cross-platform time formatting (`%-I` is a glibc extension that raises on
  Windows).

### Interface

- **New CLI**: `sail now | plan | week | compare | spots | profiles | watch`,
  replacing the old flag soup (`--today --chicago --nyc --all-delivery`, plus
  city flags parsed out of argparse's *unknown* arguments).
- **New config file** at `~/.config/sailing-conditions/config.toml` for spots,
  profiles and watch rules. Credentials remain environment-only.
- **Watch rules** replace the old alerts file: standing rules with per-date
  cooldown state, so a scheduled run cannot spam you, and failed deliveries are
  retried rather than silently marked as sent.
- **Rich terminal output** with an hourly bar chart, plus Slack Block Kit, HTML
  email and JSON renderers.
- JSON output carries a `schema_version` and includes factors, vetoes and windows.

### Removed

- The marine text-product scraper and its regular expressions.
- Non-sailing cities and their activity suggestions ("museum hop"), which had
  nothing to do with the question the tool answers.
- The Chicago-specific forecast path and its hardcoded season gate.
- `IMPROVEMENTS.md`.

### Development

- 245 tests running fully offline against recorded NOAA payloads (refresh with
  `tools/capture_fixtures.py`), ~94% coverage, `mypy --strict` clean, ruff clean,
  CI across Python 3.11-3.13.

## [0.1.0] — 2025-08-19

- Initial version: multi-city NWS text-forecast summaries with a 1-10 rating,
  delivered to Slack and email.
