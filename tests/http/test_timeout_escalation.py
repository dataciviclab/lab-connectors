"""Test timeout escalation in HttpClient.

timeout_escalation allows progressive timeout values per attempt,
useful for sources that are slow or have variable response times.
"""
from __future__ import annotations

import time
from typing import Any

import pytest
import requests

from lab_connectors.http import HttpClient

pytestmark = pytest.mark.policy


class _FakeResponse:
    def __init__(self, status_code: int = 200, content: bytes = b"ok") -> None:
        self.status_code = status_code
        self.content = content


# ---------------------------------------------------------------------------
# Escalation with timeout (requests.exceptions.Timeout / ConnectTimeout)
# ---------------------------------------------------------------------------


def test_escalation_retries_with_higher_timeout_on_timeout(monkeypatch) -> None:
    """Timeout escalation retries with next timeout value on Timeout."""
    call_timeouts = []

    def fake_get(url: str, **kw: Any) -> _FakeResponse:
        call_timeouts.append(kw.get("timeout"))
        if len(call_timeouts) < 3:
            raise requests.exceptions.Timeout("timed out")
        return _FakeResponse(200, b"ok")

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(time, "sleep", lambda secs: None)

    client = HttpClient(
        timeout_escalation=[5, 15, 30],
        max_retries=0,  # escalation overrides retry count
    )
    result = client.get("https://example.test/escalate")

    assert result.is_ok
    assert call_timeouts == [5, 15, 30], f"got {call_timeouts}"


def test_escalation_exhaustion_returns_last_error(monkeypatch) -> None:
    """When all escalation steps time out, return the last error."""
    call_timeouts = []

    def fake_get(url: str, **kw: Any) -> _FakeResponse:
        call_timeouts.append(kw.get("timeout"))
        raise requests.exceptions.Timeout("timed out")

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(time, "sleep", lambda secs: None)

    client = HttpClient(timeout_escalation=[5, 15])
    result = client.get("https://example.test/exhaust")

    assert result.is_error
    assert isinstance(result.err, requests.exceptions.Timeout)
    # Should have tried both steps
    assert call_timeouts == [5, 15], f"got {call_timeouts}"


def test_escalation_stops_on_success_before_exhaustion(monkeypatch) -> None:
    """If a middle escalation step succeeds, do not attempt further steps."""
    call_timeouts = []

    def fake_get(url: str, **kw: Any) -> _FakeResponse:
        call_timeouts.append(kw.get("timeout"))
        if len(call_timeouts) == 1:
            raise requests.exceptions.Timeout("timed out")
        return _FakeResponse(200, b"ok")

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(time, "sleep", lambda secs: None)

    client = HttpClient(timeout_escalation=[5, 15, 30])
    result = client.get("https://example.test/stop-early")

    assert result.is_ok
    assert call_timeouts == [5, 15], f"got {call_timeouts}"


# ---------------------------------------------------------------------------
# Escalation does not interfere with normal 5xx retry
# ---------------------------------------------------------------------------


def test_escalation_5xx_retry_uses_escalation_timeout(monkeypatch) -> None:
    """On 5xx, the next attempt still uses the next escalation timeout."""
    call_timeouts = []
    attempts = []

    def fake_get(url: str, **kw: Any) -> _FakeResponse:
        call_timeouts.append(kw.get("timeout"))
        attempts.append(len(attempts))
        if len(attempts) < 3:
            return _FakeResponse(503, b"down")
        return _FakeResponse(200, b"ok")

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(time, "sleep", lambda secs: None)

    client = HttpClient(timeout_escalation=[10, 20, 40])
    result = client.get("https://example.test/5xx-escalation")

    assert result.is_ok
    # Each attempt uses the corresponding escalation timeout
    assert call_timeouts == [10, 20, 40], f"got {call_timeouts}"


# ---------------------------------------------------------------------------
# Escalation with POST (opt-in retries)
# ---------------------------------------------------------------------------


def test_escalation_post_respects_retries(monkeypatch) -> None:
    """POST with escalation uses escalation timeouts when retries > 0."""
    call_timeouts = []

    def fake_post(url: str, **kw: Any) -> _FakeResponse:
        call_timeouts.append(kw.get("timeout"))
        if len(call_timeouts) < 2:
            raise requests.exceptions.Timeout("timed out")
        return _FakeResponse(200, b"ok")

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(time, "sleep", lambda secs: None)

    client = HttpClient(timeout_escalation=[5, 15, 30])
    # retries=1 → 2 attempts, but escalation needs at least 3 → 3 attempts
    result = client.post("https://example.test/post-escalate", retries=1)

    assert result.is_ok
    assert call_timeouts == [5, 15], f"got {call_timeouts}"


# ---------------------------------------------------------------------------
# No escalation = backward compatible
# ---------------------------------------------------------------------------


def test_no_escalation_uses_constant_timeout(monkeypatch) -> None:
    """Without timeout_escalation, behaviour is unchanged (all attempts same timeout)."""
    call_timeouts = []

    def fake_get(url: str, **kw: Any) -> _FakeResponse:
        call_timeouts.append(kw.get("timeout"))
        if len(call_timeouts) < 2:
            raise requests.exceptions.Timeout("timed out")
        return _FakeResponse(200, b"ok")

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(time, "sleep", lambda secs: None)

    client = HttpClient(timeout=30, max_retries=2)
    result = client.get("https://example.test/no-escalation")

    assert result.is_ok
    # Both attempts should use 30s (no escalation)
    assert call_timeouts == [30, 30], f"got {call_timeouts}"


# ---------------------------------------------------------------------------
# Escalation fallback to base timeout when list is shorter than attempts
# ---------------------------------------------------------------------------


def test_escalation_falls_back_to_base_timeout(monkeypatch) -> None:
    """When escalation list is shorter than retries, fall back to base timeout."""
    call_timeouts = []

    def fake_get(url: str, **kw: Any) -> _FakeResponse:
        call_timeouts.append(kw.get("timeout"))
        # Fail first 3 calls, succeed on the 4th
        if len(call_timeouts) < 4:
            raise requests.exceptions.Timeout("timed out")
        return _FakeResponse(200, b"ok")

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(time, "sleep", lambda secs: None)

    # escalation=[5, 10] + base timeout=30 + max_retries=4 → 4 total attempts
    # Timeouts: 5, 10, 30, 30 (fallback to base after list exhausted)
    client = HttpClient(timeout=30, timeout_escalation=[5, 10], max_retries=4)
    result = client.get("https://example.test/fallback")

    assert result.is_ok, f"got {result}"
    assert call_timeouts == [5, 10, 30, 30], f"got {call_timeouts}"


# ---------------------------------------------------------------------------
# Escalation with backoff: backoff delay is still applied between attempts
# ---------------------------------------------------------------------------


def test_escalation_still_applies_backoff(monkeypatch) -> None:
    """Backoff delay is applied between escalation attempts (like normal retry)."""
    sleeps = []

    def fake_sleep(secs: float) -> None:
        sleeps.append(secs)

    monkeypatch.setattr(time, "sleep", fake_sleep)

    def fake_get(url: str, **kw: Any) -> _FakeResponse:
        # First attempt times out, second succeeds
        if len(sleeps) == 0:
            raise requests.exceptions.Timeout("timed out")
        return _FakeResponse(200, b"ok")

    monkeypatch.setattr(requests, "get", fake_get)

    client = HttpClient(
        timeout_escalation=[5, 15],
        retry_backoff=1.0,
    )
    result = client.get("https://example.test/backoff-escalation")

    assert result.is_ok
    # attempt 1→2: single sleep(1.0) before second attempt
    assert len(sleeps) == 1, f"got {sleeps}"
    assert 0.9 <= sleeps[0] <= 1.1, f"got {sleeps[0]}"
