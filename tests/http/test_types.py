"""Tests for lab_connectors.http.types."""
from __future__ import annotations

from lab_connectors.http.types import HttpResult


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
        result = HttpResult(response=None, err=RuntimeError("boom"), ssl_fallback_used=False)
        assert result.is_error is True
        assert result.ssl_fallback_used is False

    def test_as_tuple(self) -> None:
        result = HttpResult(response="<Response 200>", err=None)
        assert result.as_tuple() == ("<Response 200>", None)

    def test_as_tuple_with_error(self) -> None:
        err = RuntimeError("boom")
        result = HttpResult(response=None, err=err)
        assert result.as_tuple() == (None, err)