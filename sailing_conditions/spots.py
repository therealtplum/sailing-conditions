"""The spot registry.

Spots are *data*, not code: the built-ins ship as a TOML file inside the
package and user spots come from the same schema in the user's config, so
adding your home water never means editing a Python dict.
"""

from __future__ import annotations

import difflib
import tomllib
from collections.abc import Iterable, Iterator, Mapping
from importlib import resources
from typing import Any

from .models import Spot

_BUILTIN_RESOURCE = "spots.toml"


class UnknownSpot(KeyError):
    """Raised when a spot key does not resolve, with a spelling hint."""

    def __init__(self, key: str, known: Iterable[str]) -> None:
        suggestions = difflib.get_close_matches(key, list(known), n=3, cutoff=0.5)
        hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        super().__init__(f"unknown spot {key!r}.{hint} Run `sail spots` for the full list.")
        self.key = key
        self.suggestions = tuple(suggestions)

    def __str__(self) -> str:  # KeyError repr-quotes its message otherwise
        return str(self.args[0])


def spot_from_mapping(key: str, data: Mapping[str, Any]) -> Spot:
    """Build a :class:`Spot` from a parsed TOML table.

    Raises:
        ValueError: if a required field is missing or a coordinate is out of range.
    """
    try:
        lat = float(data["lat"])
        lon = float(data["lon"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"spot {key!r}: lat and lon are required numbers") from exc
    if not -90.0 <= lat <= 90.0 or not -180.0 <= lon <= 180.0:
        raise ValueError(f"spot {key!r}: coordinates out of range ({lat}, {lon})")
    return Spot(
        key=key,
        name=str(data.get("name", key.replace("_", " ").title())),
        lat=lat,
        lon=lon,
        region=str(data.get("region", "")),
        blurb=str(data.get("blurb", "")),
        buoy=(str(data["buoy"]) if data.get("buoy") else None),
        timezone=(str(data["timezone"]) if data.get("timezone") else None),
        tags=tuple(str(t) for t in data.get("tags", ())),
    )


def load_spot_table(table: Mapping[str, Any]) -> dict[str, Spot]:
    """Convert a ``{key: {...}}`` mapping into spots."""
    return {key: spot_from_mapping(key, value) for key, value in table.items()}


def builtin_spots() -> dict[str, Spot]:
    """Load the packaged spot registry."""
    raw = resources.files(f"{__package__}.data").joinpath(_BUILTIN_RESOURCE).read_bytes()
    return load_spot_table(tomllib.loads(raw.decode("utf-8")).get("spots", {}))


class SpotRegistry:
    """Built-in spots overlaid with user-defined ones."""

    def __init__(self, spots: Mapping[str, Spot] | None = None) -> None:
        self._spots: dict[str, Spot] = dict(spots) if spots is not None else builtin_spots()

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and key.lower() in self._spots

    def __iter__(self) -> Iterator[Spot]:
        return iter(self._spots.values())

    def __len__(self) -> int:
        return len(self._spots)

    @property
    def keys(self) -> tuple[str, ...]:
        """All known spot keys, in registry order."""
        return tuple(self._spots)

    def merged(self, extra: Mapping[str, Spot]) -> SpotRegistry:
        """Return a new registry with ``extra`` overriding matching keys."""
        return SpotRegistry({**self._spots, **extra})

    def get(self, key: str) -> Spot:
        """Look up one spot, case-insensitively.

        Raises:
            UnknownSpot: if no spot matches, carrying near-miss suggestions.
        """
        try:
            return self._spots[key.lower().strip()]
        except KeyError:
            raise UnknownSpot(key, self._spots) from None

    def resolve(self, keys: Iterable[str]) -> list[Spot]:
        """Resolve many keys at once, preserving order and dropping duplicates."""
        seen: dict[str, Spot] = {}
        for key in keys:
            spot = self.get(key)
            seen.setdefault(spot.key, spot)
        return list(seen.values())

    def tagged(self, tag: str) -> list[Spot]:
        """All spots carrying a tag, e.g. ``great-lakes``."""
        return [s for s in self._spots.values() if tag in s.tags]
