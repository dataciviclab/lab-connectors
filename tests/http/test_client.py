"""Tests for HttpClient — post() method.

Tests mock the public boundary (requests.post), not internal HTTP details.
Retry and SSL fallback logic is tested through mocked exceptions.
"""

from __future__ import annotations

import io
import subprocess
import time
from typing import Any

import pytest
import requests

from lab_connectors.http import HttpClient
from lab_connectors.http.types import HttpFallbackError, HttpResult

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


# ---------------------------------------------------------------------------
# Proxy fallback on 403
# ---------------------------------------------------------------------------


@pytest.mark.contract
@pytest.mark.parametrize("method", ["post", "get", "head"])
def test_proxy_fallback_on_403(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
) -> None:
    """403 triggers a single extra attempt through BLOCKED_SOURCE_PROXY.

    The proxy attempt does NOT consume the retry budget — works even
    with max_retries=1.
    """
    monkeypatch.setenv("BLOCKED_SOURCE_PROXY", "http://proxy.test:8888")

    call_count: int = 0

    def fake_request(url: str, **kwargs: Any) -> _FakeResponse:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _FakeResponse(403, b"blocked")
        # Second call: verify proxy was passed
        assert kwargs.get("proxies") == {
            "http": "http://proxy.test:8888",
            "https": "http://proxy.test:8888",
        }
        return _FakeResponse(200, b"ok")

    monkeypatch.setattr(requests, method, fake_request)
    # Also patch Session method for SSL fallback compatibility
    session_attr = getattr(requests.Session, method, None)
    if session_attr:
        monkeypatch.setattr(requests.Session, method, lambda self, *a, **kw: fake_request(*a, **kw))

    client = HttpClient(max_retries=1, timeout=15)
    fn = getattr(client, method)
    result = fn("https://blocked.test/api")

    assert result.is_ok, f"{method} should succeed via proxy fallback"
    assert call_count == 2, f"{method} should retry exactly once with proxy"


@pytest.mark.contract
def test_proxy_fallback_skipped_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without BLOCKED_SOURCE_PROXY, a 403 is returned as-is."""
    call_count: int = 0

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        nonlocal call_count
        call_count += 1
        return _FakeResponse(403, b"blocked")

    monkeypatch.setattr(requests, "post", fake_post)

    client = HttpClient(max_retries=0, timeout=15)
    result = client.post("https://blocked.test/api")

    assert result.response is not None
    assert result.response.status_code == 403
    assert call_count == 1  # no retry, no proxy fallback


# ---------------------------------------------------------------------------
# Fallback extra: curl
# ---------------------------------------------------------------------------


@pytest.mark.contract
def test_via_curl_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """curl disponibile e subprocess torna exit 0 → HttpResult ok."""
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/curl" if name == "curl" else None)

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(args[0], 0, stdout=b"curl content", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)

    client = HttpClient()
    result = client._via_curl("https://example.test/file.csv")

    assert result.is_ok
    assert result.response is not None
    assert result.response.content == b"curl content"
    assert result.ssl_fallback_used is True


@pytest.mark.contract
def test_via_curl_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """curl non installato → HttpResult con errore."""
    monkeypatch.setattr("shutil.which", lambda name: None)

    client = HttpClient()
    result = client._via_curl("https://example.test/file.csv")

    assert result.is_error
    assert "curl non disponibile" in str(result.err).lower()


# ---------------------------------------------------------------------------
# Fallback extra: urllib
# ---------------------------------------------------------------------------


@pytest.mark.contract
def test_via_urllib_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """urllib.urlopen torna contenuto → HttpResult ok."""
    fake_resp = io.BytesIO(b"urllib content")

    def fake_urlopen(req: Any, timeout: Any = None, context: Any = None) -> Any:
        return fake_resp

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = HttpClient()
    result = client._via_urllib("https://example.test/file.csv")

    assert result.is_ok
    assert result.response is not None
    assert result.response.content == b"urllib content"
    assert result.ssl_fallback_used is True


@pytest.mark.contract
def test_via_urllib_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """2 fallimenti poi 1 successo → HttpResult ok al terzo tentativo."""
    attempts: list[int] = []

    class FakeUrlopen:
        def __call__(self, req: Any, timeout: Any = None, context: Any = None) -> Any:
            attempts.append(len(attempts))
            if len(attempts) < 3:
                raise Exception(f"timeout attempt {len(attempts)}")
            return io.BytesIO(b"urllib after retry")

    monkeypatch.setattr("urllib.request.urlopen", FakeUrlopen())

    client = HttpClient()
    result = client._via_urllib("https://example.test/file.csv")

    assert result.is_ok
    assert result.response is not None
    assert result.response.content == b"urllib after retry"
    assert result.ssl_fallback_used is True
    assert len(attempts) == 3


# ---------------------------------------------------------------------------
# Fallback chain: tutti falliscono
# ---------------------------------------------------------------------------


@pytest.mark.contract
def test_fallback_chain_all_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tutte le strategie falliscono → HttpResult con HttpFallbackError."""
    # Disabilita curl e urllib
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr(
        "lab_connectors.http.client.HttpClient._via_urllib",
        lambda self, url, timeout=None: HttpResult(
            response=None, err=Exception("urllib fail"), ssl_fallback_used=False
        ),
    )

    # Mock TLS 1.2 session per farlo fallire
    class FakeSession:
        def get(self, url: str, **kwargs: Any) -> Any:
            raise requests.exceptions.ConnectionError("TLS 1.2 fail")

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "lab_connectors.http.client.HttpClient._tls12_session", lambda self: FakeSession()
    )

    client = HttpClient()
    # SSL error diretto → parte la catena di fallback
    result = client._run_fallback_chain(
        "https://example.test/fail", "GET", {}, Exception("primary SSL fail"), []
    )

    assert result.is_error
    assert result.ssl_fallback_used is False
