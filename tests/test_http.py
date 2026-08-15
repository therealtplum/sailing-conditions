"""HTTP client: retries, backoff, caching."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
import requests

from sailing_conditions.sources.http import DiskCache, FetchError, HttpClient


class FakeResponse:
    def __init__(self, status: int = 200, text: str = "ok", headers: dict[str, str] | None = None) -> None:
        self.status_code = status
        self.text = text
        self.headers = headers or {}

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


class FakeSession:
    """Replays a scripted list of responses (or exceptions)."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[tuple[str, dict]] = []

    def get(self, url, **kwargs):
        self.requests.append((url, kwargs))
        result = self.responses.pop(0) if self.responses else FakeResponse()
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def sleeps() -> list[float]:
    return []


def client(session, sleeps, **kwargs) -> HttpClient:
    return HttpClient("test-agent", session=session, sleep=sleeps.append, backoff=0.1, **kwargs)


def test_sends_the_identifying_user_agent(sleeps):
    session = FakeSession(FakeResponse(text="body"))
    assert client(session, sleeps).get_text("https://example.test/x") == "body"
    assert session.requests[0][1]["headers"]["User-Agent"] == "test-agent"


def test_retries_transient_failures_then_succeeds(sleeps):
    session = FakeSession(
        requests.ConnectionError("boom"),
        FakeResponse(status=503),
        FakeResponse(text="finally"),
    )
    assert client(session, sleeps).get_text("https://example.test/x") == "finally"
    assert len(sleeps) == 2
    assert sleeps[1] > sleeps[0], "backoff should grow"


def test_gives_up_after_max_attempts(sleeps):
    session = FakeSession(*[FakeResponse(status=500) for _ in range(3)])
    with pytest.raises(FetchError) as exc:
        client(session, sleeps).get_text("https://example.test/x")
    assert exc.value.status == 500
    assert len(session.requests) == 3


def test_does_not_retry_a_client_error(sleeps):
    session = FakeSession(FakeResponse(status=404))
    with pytest.raises(FetchError) as exc:
        client(session, sleeps).get_text("https://example.test/missing")
    assert exc.value.status == 404
    assert len(session.requests) == 1, "404 will still be 404 next time"
    assert sleeps == []


def test_honors_retry_after(sleeps):
    session = FakeSession(FakeResponse(status=429, headers={"Retry-After": "7"}), FakeResponse(text="ok"))
    client(session, sleeps).get_text("https://example.test/x")
    assert sleeps == [7.0]


def test_ignores_a_malformed_retry_after(sleeps):
    session = FakeSession(FakeResponse(status=429, headers={"Retry-After": "soon"}), FakeResponse(text="ok"))
    client(session, sleeps).get_text("https://example.test/x")
    assert sleeps and sleeps[0] < 1.0


def test_get_json_parses(sleeps):
    session = FakeSession(FakeResponse(text=json.dumps({"a": 1})))
    assert client(session, sleeps).get_json("https://example.test/x") == {"a": 1}


def test_get_json_rejects_html(sleeps):
    session = FakeSession(FakeResponse(text="<html>error page</html>"))
    with pytest.raises(FetchError, match="not valid JSON"):
        client(session, sleeps).get_json("https://example.test/x")


def test_cache_serves_the_second_request(tmp_path: Path, sleeps):
    session = FakeSession(FakeResponse(text="first"), FakeResponse(text="second"))
    http = client(session, sleeps, cache=DiskCache(tmp_path))
    assert http.get_text("https://example.test/x", ttl=60) == "first"
    assert http.get_text("https://example.test/x", ttl=60) == "first"
    assert len(session.requests) == 1


def test_cache_expires(tmp_path: Path, sleeps):
    session = FakeSession(FakeResponse(text="first"), FakeResponse(text="second"))
    http = client(session, sleeps, cache=DiskCache(tmp_path))
    http.get_text("https://example.test/x", ttl=60)
    stored = next(tmp_path.glob("*.json"))
    payload = json.loads(stored.read_text())
    payload["fetched"] = time.time() - 3600
    stored.write_text(json.dumps(payload))
    assert http.get_text("https://example.test/x", ttl=60) == "second"


def test_cache_is_bypassed_without_a_ttl(tmp_path: Path, sleeps):
    session = FakeSession(FakeResponse(text="first"), FakeResponse(text="second"))
    http = client(session, sleeps, cache=DiskCache(tmp_path))
    assert http.get_text("https://example.test/x") == "first"
    assert http.get_text("https://example.test/x") == "second"


def test_corrupt_cache_entry_is_ignored(tmp_path: Path, sleeps):
    cache = DiskCache(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    cache.path_for("https://example.test/x").write_text("{ not json")
    session = FakeSession(FakeResponse(text="fresh"))
    assert client(session, sleeps, cache=cache).get_text("https://example.test/x", ttl=60) == "fresh"


def test_cache_keys_are_per_url(tmp_path: Path):
    cache = DiskCache(tmp_path)
    assert cache.path_for("https://a.test") != cache.path_for("https://b.test")
