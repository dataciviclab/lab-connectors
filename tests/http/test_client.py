"""Tests for HttpClient — post() method.

Tests mock the public boundary (requests.post), not internal HTTP details.
Retry and SSL fallback logic is tested through mocked exceptions.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
import requests

from lab_connectors.http import HttpClient
from lab_connectors.http.types import HttpFallbackError

from ..conftest import _FakeResponse

# ---------------------------------------------------------------------------
# post() — success
# ---------------------------------------------------------------------------


@pytest.mark.contract
@pytest.mark.parametrize(
    ("body_kwargs", "expect_key", "expect_val"),
    [
        ({"data": {"key": "val"}}, "data", {"key": "val"}),
        ({"json": {"query": "test"}}, "json", {"query": "test"}),
        ({}, None, None),  # no body
    ],
)
def test_post_success(
    monkeypatch: pytest.MonkeyPatch,
    body_kwargs: dict,
    expect_key: str | None,
    expect_val: Any,
) -> None:
    """POST with various body forms returns content correctly."""
    calls: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        calls.append({"url": url, **kwargs})
        return _FakeResponse(200, b"payload")

    monkeypatch.setattr(requests, "post", fake_post)

    client = HttpClient(timeout=15)
    result = client.post("https://example.test/api", **body_kwargs)

    assert result.is_ok
    assert len(calls) == 1
    assert calls[0]["url"] == "https://example.test/api"
    assert calls[0]["headers"]["User-Agent"] == client.user_agent
    if expect_key:
        assert calls[0][expect_key] == expect_val


# ---------------------------------------------------------------------------
# post() — error handling
# ---------------------------------------------------------------------------

HTTP_ERROR_SCENARIOS: list[tuple[str, str, type, str]] = [
    ("503", "service unavailable", "HttpResult with 503 response", "503"),
    ("connection refused", None, "HttpResult with err", "connection refused"),
]


@pytest.mark.contract
@pytest.mark.parametrize(
    ("error_label", "response_content", "desc", "match"),
    HTTP_ERROR_SCENARIOS,
    ids=["http_5xx", "connection_error"],
)
def test_post_errors(
    monkeypatch: pytest.MonkeyPatch,
    error_label: str,
    response_content: str | None,
    desc: str,
    match: str,
) -> None:
    """HTTP and connection errors are surfaced via HttpResult."""

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        if response_content is None:
            raise requests.exceptions.ConnectionError(error_label)
        return _FakeResponse(int(error_label), response_content.encode())

    monkeypatch.setattr(requests, "post", fake_post)

    client = HttpClient(max_retries=0)
    result = client.post("https://example.test/fail")

    if response_content is None:
        assert result.is_error
        assert match in str(result.err).lower()
    else:
        assert result.response is not None
        assert result.response.status_code == int(error_label)
        assert result.err is None


# ---------------------------------------------------------------------------
# post() — retry
# ---------------------------------------------------------------------------


@pytest.mark.adapter
def test_post_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retry opt-in: 5xx triggers retry only when retries>0."""
    monkeypatch.setattr(time, "sleep", lambda secs: None)
    attempts: list[int] = []

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        attempts.append(len(attempts))
        if len(attempts) < 2:
            return _FakeResponse(502, b"bad gateway")
        return _FakeResponse(200, b"ok-after-retry")

    monkeypatch.setattr(requests, "post", fake_post)

    client = HttpClient()
    result = client.post("https://example.test/retry", retries=2)

    assert result.is_ok
    assert result.response is not None
    assert result.response.content == b"ok-after-retry"
    assert len(attempts) == 2


# ---------------------------------------------------------------------------
# post() — caller-provided verify kwarg
# ---------------------------------------------------------------------------


@pytest.mark.policy
def test_post_verify_passed_to_primary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Caller-provided verify= is forwarded to primary requests.post()."""
    calls: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        calls.append(kwargs)
        return _FakeResponse(200, b"ok")

    monkeypatch.setattr(requests, "post", fake_post)

    client = HttpClient()
    result = client.post("https://example.test/api", verify=False)

    assert result.is_ok
    # verify must appear in kwargs forwarded to requests.post
    assert calls[0].get("verify") is False


@pytest.mark.policy
def test_post_verify_collision_free_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Caller verify= does not collide when SSL fallback triggers."""
    # Use the existing SSL fallback success test but with verify=True
    attempts: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        attempts.append(kwargs)
        # Simulate SSL error when verify is not explicitly False
        if kwargs.get("verify", True) is not False:
            raise requests.exceptions.SSLError("certificate verify failed")
        return _FakeResponse(200, b"ok")

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(requests.Session, "post", lambda self, *a, **kw: fake_post(*a, **kw))

    client = HttpClient()
    # Caller passes verify=True — does NOT collide with fallback verify=False
    result = client.post("https://example.test/api", verify=True)

    assert result.is_ok
    # Primary call forwarded verify=True to requests.post
    assert any(a.get("verify") is True for a in attempts)
    # Fallback reached without TypeError
    assert any(a.get("verify") is False for a in attempts)
    assert result.ssl_fallback_used is True


# ---------------------------------------------------------------------------
# post() — SSL fallback
# ---------------------------------------------------------------------------


def _patch_session_post(monkeypatch: pytest.MonkeyPatch, fake_post) -> None:
    """Patch both requests.post (primary) and Session.post (fallback).

    Session.post is a bound method that passes self first, hence the lambda wrapper.
    """
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(requests.Session, "post", lambda self, *a, **kw: fake_post(*a, **kw))


@pytest.mark.adapter
def test_post_ssl_fallback_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """SSLError triggers SSL fallback; fallback succeeds."""
    attempts: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        attempts.append(kwargs)
        if kwargs.get("verify", True) is True:
            raise requests.exceptions.SSLError("certificate verify failed")
        return _FakeResponse(200, b"ssl-fallback-data")

    _patch_session_post(monkeypatch, fake_post)

    client = HttpClient(max_retries=1)
    result = client.post("https://example.test/ssl-expired", data={"x": "1"})

    assert result.is_ok
    assert result.response is not None
    assert result.response.content == b"ssl-fallback-data"
    assert result.ssl_fallback_used is True
    assert len([a for a in attempts if a.get("verify") is False]) == 1


@pytest.mark.adapter
def test_post_ssl_fallback_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """SSL fallback also fails → HttpResult with HttpFallbackError."""

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        if kwargs.get("verify", True) is True:
            raise requests.exceptions.SSLError("certificate verify failed")
        raise requests.exceptions.ConnectionError("fallback also failed")

    _patch_session_post(monkeypatch, fake_post)

    client = HttpClient(max_retries=1)
    result = client.post("https://example.test/ssl-fail")

    assert result.is_error
    assert isinstance(result.err, HttpFallbackError)


# ---------------------------------------------------------------------------
# post() — user-agent passthrough
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("user_agent", "expected"),
    [
        ("custom-agent/1.0", "custom-agent/1.0"),
        (None, "DataCivicLab-HttpClient/0.1"),
    ],
    ids=["custom", "default"],
)
@pytest.mark.policy
def test_post_user_agent(
    monkeypatch: pytest.MonkeyPatch,
    user_agent: str | None,
    expected: str,
) -> None:
    """User-Agent is forwarded to POST requests."""
    calls: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        calls.append(kwargs)
        return _FakeResponse(200, b"ok")

    monkeypatch.setattr(requests, "post", fake_post)

    client = HttpClient(user_agent=user_agent) if user_agent else HttpClient()
    client.post("https://example.test/api")

    assert calls[0]["headers"]["User-Agent"] == expected
