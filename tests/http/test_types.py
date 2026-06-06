"""Tests for lab_connectors.http.types."""

from __future__ import annotations

import pytest

from lab_connectors.http.types import HttpFallbackError, HttpResult

pytestmark = pytest.mark.pure_unit


class TestHttpFallbackError:
    def test_str_contains_class_names(self) -> None:
        primary = RuntimeError("primary")
        fallback = RuntimeError("fallback")
        err = HttpFallbackError(primary_error=primary, fallback_error=fallback)
        s = str(err)
        assert "RuntimeError" in s
        assert "primary" in s
        assert "fallback" in s

    def test_attributes_accessible(self) -> None:
        primary = ValueError("primary")
        fallback = TimeoutError("fallback")
        err = HttpFallbackError(primary_error=primary, fallback_error=fallback)
        assert err.primary_error is primary
        assert err.fallback_error is fallback


class TestHttpResult:
    def test_ok_response(self) -> None:
        result = HttpResult(response="<Response 200>", err=None)
        assert result.is_ok is True
        assert result.is_error is False
        assert result.ssl_fallback_used is None

    def test_error_response(self) -> None:
        result = HttpResult(response=None, err=RuntimeError("boom"))
        assert result.is_ok is False
        assert result.is_error is True

    def test_ssl_fallback_success(self) -> None:
        result = HttpResult(response="<Response 200>", err=None, ssl_fallback_used=True)
        assert result.is_ok is True
        assert result.ssl_fallback_used is True

    def test_ssl_fallback_failed(self) -> None:
        err = HttpFallbackError(
            primary_error=RuntimeError("primary"),
            fallback_error=RuntimeError("fallback"),
        )
        result = HttpResult(response=None, err=err, ssl_fallback_used=False)
        assert result.is_error is True
        assert result.ssl_fallback_used is False

    def test_is_ssl_fallback_failed_true(self) -> None:
        err = HttpFallbackError(
            primary_error=RuntimeError("primary"),
            fallback_error=RuntimeError("fallback"),
        )
        result = HttpResult(response=None, err=err, ssl_fallback_used=False)
        assert result.is_ssl_fallback_failed is True

    def test_is_ssl_fallback_failed_false_when_ok(self) -> None:
        result = HttpResult(response="<Response 200>", err=None, ssl_fallback_used=None)
        assert result.is_ssl_fallback_failed is False

    def test_is_ssl_fallback_failed_false_when_fallback_ok(self) -> None:
        result = HttpResult(response="<Response 200>", err=None, ssl_fallback_used=True)
        assert result.is_ssl_fallback_failed is False

    def test_as_tuple(self) -> None:
        result = HttpResult(response="<Response 200>", err=None)
        assert result.as_tuple() == ("<Response 200>", None)

    def test_as_tuple_with_error(self) -> None:
        err = RuntimeError("boom")
        result = HttpResult(response=None, err=err)
        assert result.as_tuple() == (None, err)
