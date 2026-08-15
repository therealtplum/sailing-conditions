"""HTTP plumbing: retries, backoff and an on-disk cache.

Two rules govern this module.

*Be a good citizen.* api.weather.gov is a free public service that asks for
an identifying User-Agent and rate-limits abusers. Responses are cached to
disk with a TTL, so re-running the CLI five times while tuning a profile
costs one request, not five.

*Be injectable.* Everything above this layer depends on the
:class:`Fetcher` protocol, never on ``requests``. That is what lets the
entire test suite run against recorded fixtures with no network and no
mocking library.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import requests

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15.0
DEFAULT_ATTEMPTS = 3
RETRY_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


class FetchError(RuntimeError):
    """A request failed after exhausting retries."""

    def __init__(self, url: str, message: str, status: int | None = None) -> None:
        super().__init__(f"{message} ({url})")
        self.url = url
        self.status = status


class Fetcher(Protocol):
    """The only interface the source layer needs from the network."""

    def get_text(self, url: str, *, ttl: float | None = None) -> str:
        """Fetch a URL as text, optionally serving from cache within ``ttl`` seconds."""
        ...

    def get_json(self, url: str, *, ttl: float | None = None) -> Any:
        """Fetch and parse a JSON document."""
        ...


@dataclass(frozen=True, slots=True)
class DiskCache:
    """A dead-simple content cache keyed by URL hash.

    Entries are plain JSON so you can read them while debugging, and stale
    entries are simply ignored rather than swept — the directory is small
    and the OS temp cleaner is welcome to it.
    """

    directory: Path

    def path_for(self, url: str) -> Path:
        """Cache file path for a URL."""
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        return self.directory / f"{digest}.json"

    def get(self, url: str, ttl: float) -> str | None:
        """Return the cached body if it exists and is younger than ``ttl``."""
        if ttl <= 0:
            return None
        path = self.path_for(url)
        try:
            payload = json.loads(path.read_text("utf-8"))
            if time.time() - float(payload["fetched"]) > ttl:
                return None
            return str(payload["body"])
        except (OSError, ValueError, KeyError):
            return None

    def put(self, url: str, body: str) -> None:
        """Store a body, ignoring any filesystem failure — a cache is a nicety."""
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            tmp = self.path_for(url).with_suffix(".tmp")
            tmp.write_text(
                json.dumps({"url": url, "fetched": time.time(), "body": body}),
                encoding="utf-8",
            )
            tmp.replace(self.path_for(url))
        except OSError as exc:  # pragma: no cover - platform dependent
            log.debug("cache write failed for %s: %s", url, exc)


class HttpClient:
    """A small retrying HTTP client with an optional disk cache."""

    def __init__(
        self,
        user_agent: str,
        *,
        cache: DiskCache | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_attempts: int = DEFAULT_ATTEMPTS,
        backoff: float = 0.75,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.user_agent = user_agent
        self.cache = cache
        self.timeout = timeout
        self.max_attempts = max(1, max_attempts)
        self.backoff = backoff
        self.session = session or requests.Session()
        self._sleep = sleep

    def get_text(self, url: str, *, ttl: float | None = None) -> str:
        """Fetch a URL, serving from cache when a fresh entry exists.

        Raises:
            FetchError: on a non-retryable status or after the last retry.
        """
        if self.cache is not None and ttl:
            cached = self.cache.get(url, ttl)
            if cached is not None:
                log.debug("cache hit %s", url)
                return cached

        body = self._request(url)
        if self.cache is not None and ttl:
            self.cache.put(url, body)
        return body

    def get_json(self, url: str, *, ttl: float | None = None) -> Any:
        """Fetch a URL and parse it as JSON.

        Raises:
            FetchError: on transport failure or malformed JSON.
        """
        text = self.get_text(url, ttl=ttl)
        try:
            return json.loads(text)
        except ValueError as exc:
            raise FetchError(url, f"response was not valid JSON: {exc}") from exc

    def _request(self, url: str) -> str:
        last_error = "unknown error"
        status: int | None = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.get(
                    url,
                    timeout=self.timeout,
                    headers={"User-Agent": self.user_agent, "Accept": "application/geo+json, */*"},
                )
                status = response.status_code
                if response.ok:
                    return response.text
                if status not in RETRY_STATUSES:
                    raise FetchError(url, f"HTTP {status}", status)
                last_error = f"HTTP {status}"
                delay = self._retry_after(response) or self._delay(attempt)
            except requests.RequestException as exc:
                last_error = str(exc) or exc.__class__.__name__
                delay = self._delay(attempt)

            if attempt == self.max_attempts:
                break
            log.warning("%s — retrying in %.1fs (%d/%d): %s", last_error, delay, attempt, self.max_attempts, url)
            self._sleep(delay)

        raise FetchError(url, f"giving up after {self.max_attempts} attempts: {last_error}", status)

    def _delay(self, attempt: int) -> float:
        """Exponential backoff with jitter, so parallel spots do not sync up."""
        return float(self.backoff * (2 ** (attempt - 1)) * (1.0 + random.random() * 0.25))

    @staticmethod
    def _retry_after(response: requests.Response) -> float | None:
        """Honor a numeric ``Retry-After`` header when the server sends one."""
        raw = response.headers.get("Retry-After")
        try:
            return max(0.0, float(str(raw))) if raw else None
        except ValueError:
            return None
