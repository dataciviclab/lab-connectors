"""Tests for FakeHttpClient — always runs in CI (no SMOKE_TESTS needed).

Covers:
- Basic GET/HEAD/POST response matching
- Error responses (is_error)
- SSL fallback flag passthrough
- Callable response resolver
- Context manager
- Request log
- Missing URL error
- fake_response() factory helpers
- _FakeResponse.raise_for_status()
"""
from __future__ import annotations

import pytest

from lab_connectors.http import HttpResult
from lab_connectors.testing import FakeHttpClient, fake_response


# ------------------------------------------------------------------
# Basic request matching
# ------------------------------------------------------------------


def test_get_matches_url():
    """GET returns the HttpResult registered for that URL."""
    fake = FakeHttpClient()
    fake.responses["https://example.test/a"] = HttpResult(
        response=fake_response(200, "alpha"), err=None,
    )
    fake.responses["https://example.test/b"] = HttpResult(
        response=fake_response(404, "not found"), err=None,
    )

    r1 = fake.get("https://example.test/a")
    assert r1.is_ok and r1.response is not None
    assert r1.response.text == "alpha"

    r2 = fake.get("https://example.test/b")
    assert r2.is_ok
    assert r2.response.status_code == 404  # type: ignore[union-attr]


def test_head_returns_pre_registered():
    """HEAD returns the registered response."""
    fake = FakeHttpClient()
    fake.responses["https://example.test/h"] = HttpResult(
        response=fake_response(200, "head-body"), err=None,
    )
    result = fake.head("https://example.test/h")
    assert result.is_ok
    assert result.response is not None


def test_post_returns_pre_registered():
    """POST returns the registered response."""
    fake = FakeHttpClient()
    fake.responses["https://example.test/p"] = HttpResult(
        response=fake_response(201, "created"), err=None,
    )
    result = fake.post("https://example.test/p", json={"key": "val"})
    assert result.is_ok
    assert result.response.status_code == 201  # type: ignore[union-attr]


# ------------------------------------------------------------------
# Error responses
# ------------------------------------------------------------------


def test_connection_error():
    """HttpResult with err=None response → is_error."""
    fake = FakeHttpClient()
    fake.responses["https://example.test/err"] = HttpResult(
        response=None, err=ConnectionError("refused"),
    )
    result = fake.get("https://example.test/err")
    assert result.is_error
    assert "refused" in str(result.err)


def test_ssl_fallback_flag_preserved():
    """ssl_fallback_used flag is preserved through the fake."""
    fake = FakeHttpClient()
    for flag in (None, True, False):
        fake.responses[f"https://example.test/f{flag}"] = HttpResult(
            response=fake_response(200) if flag is not False else None,
            err=None if flag is not False else Exception("fail"),
            ssl_fallback_used=flag,
        )
        result = fake.get(f"https://example.test/f{flag}")
        assert result.ssl_fallback_used == flag


# ------------------------------------------------------------------
# Callable response resolver
# ------------------------------------------------------------------


def test_callable_response():
    """If the registered value is callable, it's invoked with (url, **kwargs)."""
    fake = FakeHttpClient()
    calls: list[tuple] = []

    def resolver(url: str, **kwargs):
        calls.append((url, kwargs))
        return HttpResult(response=fake_response(200, "from-callable"), err=None)

    fake.responses["https://example.test/c"] = resolver
    result = fake.get("https://example.test/c", extra="param")

    assert result.response.text == "from-callable"  # type: ignore[union-attr]
    assert len(calls) == 1
    assert calls[0][0] == "https://example.test/c"
    assert calls[0][1]["extra"] == "param"


# ------------------------------------------------------------------
# Request log
# ------------------------------------------------------------------


def test_request_log_tracks_all_calls():
    """Every request is logged with (method, url, kwargs)."""
    fake = FakeHttpClient()
    fake.responses["https://example.test/r"] = HttpResult(
        response=fake_response(200), err=None,
    )
    fake.get("https://example.test/r", a=1)
    fake.head("https://example.test/r", b=2)
    fake.post("https://example.test/r", data="x", c=3)

    assert len(fake.requests) == 3
    assert fake.requests[0] == ("GET", "https://example.test/r", {"a": 1})
    assert fake.requests[1] == ("HEAD", "https://example.test/r", {"b": 2})
    assert fake.requests[2][0] == "POST"
    assert fake.requests[2][1] == "https://example.test/r"


# ------------------------------------------------------------------
# Context manager
# ------------------------------------------------------------------


def test_context_manager():
    """FakeHttpClient works as a context manager (no-op)."""
    with FakeHttpClient() as fake:
        fake.responses["https://example.test/cm"] = HttpResult(
            response=fake_response(200), err=None,
        )
        result = fake.get("https://example.test/cm")
        assert result.is_ok


# ------------------------------------------------------------------
# Missing URL
# ------------------------------------------------------------------


def test_missing_url_raises_keyerror():
    """Accessing an unregistered URL raises KeyError with helpful message."""
    fake = FakeHttpClient()
    fake.responses["https://example.test/existing"] = HttpResult(
        response=fake_response(200), err=None,
    )
    with pytest.raises(KeyError, match="No response registered"):
        fake.get("https://example.test/missing")


# ------------------------------------------------------------------
# fake_response factory
# ------------------------------------------------------------------


def test_fake_response_json():
    """fake_response with json_data → .json() returns parsed data."""
    resp = fake_response(200, json_data={"key": "val"})
    assert resp.json() == {"key": "val"}
    assert resp.status_code == 200


def test_fake_response_text_content():
    """fake_response text → .text and .content."""
    resp = fake_response(200, text="hello")
    assert resp.text == "hello"
    assert resp.content == b"hello"


def test_fake_response_raise_for_status():
    """raise_for_status on non-ok response raises _FakeHTTPError."""
    resp = fake_response(403, text="forbidden")
    import requests
    with pytest.raises(requests.HTTPError, match="HTTP 403"):
        resp.raise_for_status()


def test_fake_response_ok_does_not_raise():
    """raise_for_status on 200 does nothing."""
    resp = fake_response(200)
    resp.raise_for_status()  # should not raise


# ------------------------------------------------------------------
# Initialization params
# ------------------------------------------------------------------


def test_init_params_stored():
    """Constructor arguments are stored as attributes (interface compat)."""
    fake = FakeHttpClient(timeout=30, max_retries=5, retry_backoff=2.5,
                          user_agent="test-agent/1.0")
    assert fake.timeout == 30
    assert fake.max_retries == 5
    assert fake.retry_backoff == 2.5
    assert fake.user_agent == "test-agent/1.0"


def test_default_user_agent():
    """Default user_agent is set."""
    fake = FakeHttpClient()
    assert fake.user_agent == "DataCivicLab-FakeHttpClient/0.1"
