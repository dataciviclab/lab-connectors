"""Minimal tests for backoff and 429 Retry-After in HttpClient."""
from __future__ import annotations

import random
import time
from typing import Any

import pytest
import requests

from lab_connectors.http import HttpClient

from ..conftest import _FakeResponse

pytestmark = pytest.mark.policy  # backoff, jitter e retry sono regole non ovvie


def test_backoff_delays_on_retry(monkeypatch) -> None:
    """Backoff sleep before each retry."""
    sleeps = []

    def fake_sleep(secs: float) -> None:
        sleeps.append(secs)

    monkeypatch.setattr(time, "sleep", fake_sleep)

    def fake_get(url: str, **kw: Any) -> _FakeResponse:
        return _FakeResponse(503, b"down")

    monkeypatch.setattr(requests, "get", fake_get)

    client = HttpClient(max_retries=3, retry_backoff=1.0)
    client.get("https://example.test/x")

    # attempt=1: sleep(1.0), attempt=2: sleep(2.0)
    assert sleeps == [1.0, 2.0], f"got {sleeps}"


def test_backoff_custom_base(monkeypatch) -> None:
    """Custom backoff changes delay scale."""
    sleeps = []

    def fake_sleep(secs: float) -> None:
        sleeps.append(secs)

    monkeypatch.setattr(time, "sleep", fake_sleep)

    def fake_get(url: str, **kw: Any) -> _FakeResponse:
        return _FakeResponse(503, b"down")

    monkeypatch.setattr(requests, "get", fake_get)

    client = HttpClient(max_retries=3, retry_backoff=2.0)
    client.get("https://example.test/x")

    assert sleeps == [2.0, 4.0], f"got {sleeps}"


def test_429_retry_after_integer(monkeypatch) -> None:
    """429 with Retry-After seconds waits that long."""
    sleeps = []
    attempts = []

    def fake_sleep(secs: float) -> None:
        sleeps.append(secs)

    monkeypatch.setattr(time, "sleep", fake_sleep)

    def fake_get(url: str, **kw: Any) -> _FakeResponse:
        attempts.append(len(attempts))
        if len(attempts) < 2:
            return _FakeResponse(429, b"slow down", headers={"Retry-After": "3"})
        return _FakeResponse(200, b"ok")

    monkeypatch.setattr(requests, "get", fake_get)

    client = HttpClient(max_retries=2)
    result = client.get("https://example.test/rl")

    assert result.is_ok
    assert len(attempts) == 2
    # Retry-After (3s) overrides backoff (1s)
    assert 2.9 <= sleeps[0] <= 3.1, f"got {sleeps[0]}"


def test_429_no_header_falls_back_to_backoff(monkeypatch) -> None:
    """429 without Retry-After uses regular backoff."""
    sleeps = []
    attempts = []

    def fake_sleep(secs: float) -> None:
        sleeps.append(secs)

    monkeypatch.setattr(time, "sleep", fake_sleep)

    def fake_get(url: str, **kw: Any) -> _FakeResponse:
        attempts.append(len(attempts))
        if len(attempts) < 2:
            return _FakeResponse(429, b"slow down")  # no Retry-After header
        return _FakeResponse(200, b"ok")

    monkeypatch.setattr(requests, "get", fake_get)

    client = HttpClient(max_retries=2, retry_backoff=1.0)
    client.get("https://example.test/rl2")

    assert len(sleeps) == 1
    assert 0.9 <= sleeps[0] <= 1.1, f"got {sleeps[0]}"


def test_post_respects_retry_backoff(monkeypatch) -> None:
    """POST with retries also uses backoff."""
    sleeps = []

    def fake_sleep(secs: float) -> None:
        sleeps.append(secs)

    monkeypatch.setattr(time, "sleep", fake_sleep)

    def fake_post(url: str, **kw: Any) -> _FakeResponse:
        return _FakeResponse(502, b"bad")

    monkeypatch.setattr(requests, "post", fake_post)

    client = HttpClient(retry_backoff=1.0)
    client.post("https://example.test/x", retries=2)

    assert sleeps == [1.0], f"got {sleeps}"


def test_jitter_applied_when_enabled(monkeypatch) -> None:
    """Jitter randomises backoff delay when retry_jitter > 0."""
    sleeps = []

    def fake_sleep(secs: float) -> None:
        sleeps.append(secs)

    monkeypatch.setattr(time, "sleep", fake_sleep)

    # Fix random.uniform to return upper bound (max jitter)
    def fake_uniform(lo: float, hi: float) -> float:
        return hi

    monkeypatch.setattr(random, "uniform", fake_uniform)

    def fake_get(url: str, **kw: Any) -> _FakeResponse:
        return _FakeResponse(503, b"down")

    monkeypatch.setattr(requests, "get", fake_get)

    # retry_jitter=0.5 → delay * uniform(0.5, 1.5) → returns hi = 1.5
    # attempt 1: delay=1.0 → 1.0 * 1.5 = 1.5
    # attempt 2: delay=2.0 → 2.0 * 1.5 = 3.0
    client = HttpClient(max_retries=3, retry_backoff=1.0, retry_jitter=0.5)
    client.get("https://example.test/jitter")

    assert len(sleeps) == 2, f"got {len(sleeps)}"
    assert abs(sleeps[0] - 1.5) < 0.01, f"got {sleeps[0]}"
    assert abs(sleeps[1] - 3.0) < 0.01, f"got {sleeps[1]}"


def test_default_jitter_no_random_called(monkeypatch) -> None:
    """Default retry_jitter=0.0 does not call random.uniform."""
    uniform_called = False

    def fake_uniform(lo: float, hi: float) -> float:
        nonlocal uniform_called
        uniform_called = True
        return (lo + hi) / 2.0

    monkeypatch.setattr(random, "uniform", fake_uniform)
    monkeypatch.setattr(time, "sleep", lambda secs: None)

    def fake_get(url: str, **kw: Any) -> _FakeResponse:
        return _FakeResponse(503, b"down")

    monkeypatch.setattr(requests, "get", fake_get)

    client = HttpClient(max_retries=3, retry_backoff=1.0)  # default jitter=0
    client.get("https://example.test/no-jitter")

    assert not uniform_called, "random.uniform should not be called with default jitter"
