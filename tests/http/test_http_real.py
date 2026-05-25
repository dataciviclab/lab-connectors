"""Integration test: HttpClient against a real public endpoint.

This test makes an actual HTTP GET request to a stable public service
(``httpbun.com``) to verify that ``HttpClient`` works end-to-end with
a real network stack — retry, timeout, SSL, and response parsing.

The test is **skipped by default** (use ``SMOKE_TESTS=1`` env var to
enable) and is intended to be run on a schedule or on-demand to detect
upstream changes (network, TLS, API contract) that mock-based tests
cannot catch.
"""
from __future__ import annotations

import os

import pytest

from lab_connectors.http import HttpClient
from lab_connectors.http.types import HttpResult


@pytest.mark.smoke
def test_http_client_get_httpbun() -> None:
    """GET httpbun.com/get → 200 + valid JSON with 'url' key."""
    _require_smoke_env()

    client = HttpClient(timeout=10, max_retries=1)
    result = client.get("https://httpbun.com/get")

    _assert_result_ok(result)
    assert result.response is not None
    data = result.response.json()
    assert isinstance(data, dict)
    assert "url" in data
    assert data["url"] == "https://httpbun.com/get"


@pytest.mark.smoke
def test_http_client_head_httpbun() -> None:
    """HEAD httpbun.com/get → 200."""
    _require_smoke_env()

    client = HttpClient(timeout=10, max_retries=1)
    result = client.head("https://httpbun.com/get")

    assert result.is_ok
    assert result.response is not None
    assert result.response.status_code == 200


@pytest.mark.smoke
def test_http_client_404_returns_is_ok_with_status() -> None:
    """GET a non-existent path → response with 404, not an error."""
    _require_smoke_env()

    client = HttpClient(timeout=10, max_retries=1)
    result = client.get("https://httpbun.com/status/404")

    # HttpResult.is_ok means we got a response (not a network error)
    assert result.is_ok
    assert result.response is not None
    assert result.response.status_code == 404


@pytest.mark.smoke
def test_http_client_429_returns_too_many_requests() -> None:
    """Simulate 429 via httpbun — response has status 429, not a network error."""
    _require_smoke_env()

    client = HttpClient(timeout=10, max_retries=1)
    result = client.get("https://httpbun.com/status/429")

    assert result.is_ok
    assert result.response is not None
    assert result.response.status_code == 429


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _require_smoke_env() -> None:
    """Skip test unless ``SMOKE_TESTS=1`` is set in the environment.

    This prevents accidental execution in PR CI while allowing
    scheduled or manual runs.
    """
    if not os.environ.get("SMOKE_TESTS"):
        pytest.skip("SMOKE_TESTS not set — integration test skipped. "
                     "Set SMOKE_TESTS=1 to enable.")


def _assert_result_ok(result: HttpResult) -> None:
    """Assert the result is usable (network + HTTP success)."""
    assert result.is_ok, (
        f"HTTP request failed: {result.err}. "
        f"SSL fallback: {result.ssl_fallback_used}"
    )
    assert result.response is not None
    assert result.response.status_code == 200
