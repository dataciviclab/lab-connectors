"""Tests for HttpClient — get() and head() methods.

Tests mock requests.get / requests.head (primary) and
requests.Session.get / requests.Session.head (SSL fallback).
"""

from __future__ import annotations

import time

import pytest
import requests

from lab_connectors.http import HttpClient
from lab_connectors.http.types import HttpFallbackError

from ..conftest import _FakeResponse

pytestmark = pytest.mark.adapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_both_get(monkeypatch, fake_get) -> None:
    """Patch requests.get (primary) and Session.get (SSL fallback)."""
    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(requests.Session, "get", lambda self, *a, **kw: fake_get(*a, **kw))


def _patch_both_head(monkeypatch, fake_head) -> None:
    """Patch requests.head (primary) and Session.head (SSL fallback)."""
    monkeypatch.setattr(requests, "head", fake_head)
    monkeypatch.setattr(requests.Session, "head", lambda self, *a, **kw: fake_head(*a, **kw))


# ===========================================================================
# GET
# ===========================================================================


def test_get_success(monkeypatch) -> None:
    calls: list[dict] = []

    def fake(url, **kw):
        calls.append({"url": url, **kw})
        return _FakeResponse(200, b"payload")

    monkeypatch.setattr(requests, "get", fake)
    client = HttpClient(timeout=15)
    result = client.get("https://example.test/data.csv")

    assert result.is_ok
    assert result.response.content == b"payload"
    assert len(calls) == 1
    assert result.ssl_fallback_used is None


def test_get_5xx_then_success(monkeypatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda secs: None)
    attempts = []

    def fake(url, **kw):
        attempts.append(len(attempts))
        if len(attempts) < 2:
            return _FakeResponse(502, b"bad gateway")
        return _FakeResponse(200, b"ok")

    monkeypatch.setattr(requests, "get", fake)

    client = HttpClient(max_retries=2)
    result = client.get("https://example.test/flaky")
    assert result.is_ok
    assert result.response.content == b"ok"
    assert len(attempts) == 2


def test_get_5xx_exhaustion_returns_last_response(monkeypatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda secs: None)
    attempts = []

    def fake(url, **kw):
        attempts.append(len(attempts))
        return _FakeResponse(503, b"down")

    monkeypatch.setattr(requests, "get", fake)

    client = HttpClient(max_retries=2)
    result = client.get("https://example.test/down")
    assert result.is_ok
    assert result.response.status_code == 503
    assert len(attempts) == 2


def test_get_no_retry_on_4xx(monkeypatch) -> None:
    calls = []

    def fake(url, **kw):
        calls.append(1)
        return _FakeResponse(404, b"not found")

    monkeypatch.setattr(requests, "get", fake)

    client = HttpClient(max_retries=3)
    result = client.get("https://example.test/notfound")

    assert result.is_ok
    assert result.response.status_code == 404
    assert len(calls) == 1


def test_get_connection_error_retry(monkeypatch) -> None:
    """Connection error triggers retry with backoff."""
    monkeypatch.setattr(time, "sleep", lambda secs: None)
    attempts = []

    def fake(url, **kw):
        attempts.append(len(attempts))
        if len(attempts) < 2:
            raise requests.ConnectionError("refused")
        return _FakeResponse(200, b"ok")

    monkeypatch.setattr(requests, "get", fake)

    client = HttpClient(max_retries=2)
    result = client.get("https://example.test/reset")

    assert result.is_ok
    assert len(attempts) == 2


def test_get_connection_error_exhaustion(monkeypatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda secs: None)
    attempts = []

    def fake(url, **kw):
        attempts.append(len(attempts))
        raise requests.ConnectionError("dead")

    monkeypatch.setattr(requests, "get", fake)

    client = HttpClient(max_retries=2)
    result = client.get("https://example.test/dead")

    assert result.is_error
    assert isinstance(result.err, requests.exceptions.ConnectionError)
    assert len(attempts) == 2


def test_get_ssl_fallback_success(monkeypatch) -> None:
    attempts = []

    def fake(url, **kw):
        attempts.append(kw)
        if kw.get("verify", True) is True:
            raise requests.exceptions.SSLError("verify failed")
        return _FakeResponse(200, b"ssl-data")

    _patch_both_get(monkeypatch, fake)

    client = HttpClient()
    result = client.get("https://example.test/ssl-expired")

    assert result.is_ok
    assert result.response.content == b"ssl-data"
    assert result.ssl_fallback_used is True


def test_get_ssl_fallback_failure(monkeypatch) -> None:
    def fake(url, **kw):
        if kw.get("verify", True) is True:
            raise requests.exceptions.SSLError("verify failed")
        raise requests.exceptions.ConnectionError("fallback also failed")

    _patch_both_get(monkeypatch, fake)

    client = HttpClient()
    result = client.get("https://example.test/ssl-fail")

    assert result.is_error
    assert isinstance(result.err, HttpFallbackError)


def test_get_max_retries_zero(monkeypatch) -> None:
    calls = []

    def fake(url, **kw):
        calls.append(1)
        return _FakeResponse(502, b"bad")

    monkeypatch.setattr(requests, "get", fake)

    client = HttpClient(max_retries=0)
    result = client.get("https://example.test/zero")

    assert result.is_ok
    assert result.response.status_code == 502
    assert len(calls) == 1


def test_get_user_agent(monkeypatch) -> None:
    calls = []

    def fake(url, **kw):
        calls.append(kw)
        return _FakeResponse(200, b"ok")

    monkeypatch.setattr(requests, "get", fake)

    client = HttpClient()
    client.get("https://example.test/api")

    assert calls[0]["headers"]["User-Agent"] == client.DEFAULT_USER_AGENT


# ===========================================================================
# HEAD
# ===========================================================================


def test_head_success(monkeypatch) -> None:
    calls = []

    def fake(url, **kw):
        calls.append(url)
        return _FakeResponse(200, b"")

    monkeypatch.setattr(requests, "head", fake)

    client = HttpClient()
    result = client.head("https://example.test/probe")

    assert result.is_ok
    assert result.response.status_code == 200
    assert len(calls) == 1


def test_head_ssl_fallback_success(monkeypatch) -> None:
    """Fixed: allow_redirects collision bug — now works."""
    attempts = []

    def fake(url, **kw):
        attempts.append(kw)
        if kw.get("verify", True) is True:
            raise requests.exceptions.SSLError("verify failed")
        return _FakeResponse(200, b"")

    _patch_both_head(monkeypatch, fake)

    client = HttpClient()
    result = client.head("https://example.test/ssl-expired")

    assert result.is_ok
    assert result.ssl_fallback_used is True
    assert any(a.get("verify") is False for a in attempts)


def test_head_ssl_fallback_failure(monkeypatch) -> None:
    def fake(url, **kw):
        if kw.get("verify", True) is True:
            raise requests.exceptions.SSLError("verify failed")
        raise requests.exceptions.ConnectionError("fallback failed")

    _patch_both_head(monkeypatch, fake)

    client = HttpClient()
    result = client.head("https://example.test/ssl-fail")

    assert result.is_error
    assert isinstance(result.err, HttpFallbackError)


def test_head_connection_error_retry(monkeypatch) -> None:
    """Head now retries on connection errors (like GET)."""
    monkeypatch.setattr(time, "sleep", lambda secs: None)
    attempts = []

    def fake(url, **kw):
        attempts.append(len(attempts))
        if len(attempts) < 2:
            raise requests.ConnectionError("refused")
        return _FakeResponse(200, b"")

    monkeypatch.setattr(requests, "head", fake)

    client = HttpClient(max_retries=2)
    result = client.head("https://example.test/dead")

    assert result.is_ok
    assert len(attempts) == 2


def test_head_user_agent(monkeypatch) -> None:
    calls = []

    def fake(url, **kw):
        calls.append(kw)
        return _FakeResponse(200, b"")

    monkeypatch.setattr(requests, "head", fake)

    client = HttpClient()
    client.head("https://example.test/probe")

    assert calls[0]["headers"]["User-Agent"] == client.DEFAULT_USER_AGENT


# ===========================================================================
# close() and context manager
# ===========================================================================


def test_close_releases_session(monkeypatch) -> None:
    """close() calls Session.close()."""
    closed = []

    class FakeSession:
        headers: dict = {}

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(requests, "Session", FakeSession)

    client = HttpClient()
    client.close()
    assert closed == [True]


def test_context_manager_calls_close(monkeypatch) -> None:
    """Using HttpClient as context manager closes session on exit."""
    closed = []

    class FakeSession:
        headers: dict = {}

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(requests, "Session", FakeSession)
    monkeypatch.setattr(requests, "get", lambda *a, **kw: _FakeResponse(200))

    with HttpClient() as client:
        client.get("https://example.test")

    assert closed == [True]
