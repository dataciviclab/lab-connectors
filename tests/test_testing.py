"""Tests per lab_connectors.testing."""
from __future__ import annotations

import pytest

from lab_connectors.http.types import HttpFallbackError
from lab_connectors.testing import FakeResponse, http_error, http_ok


class TestFakeResponse:
    def test_defaults(self) -> None:
        resp = FakeResponse()
        assert resp.status_code == 200
        assert resp.content == b""
        assert resp.headers == {}
        assert resp.url == ""

    def test_custom_values(self) -> None:
        resp = FakeResponse(
            status_code=404,
            content=b"not found",
            headers={"Content-Type": "text/plain"},
            url="https://example.test/missing",
        )
        assert resp.status_code == 404
        assert resp.content == b"not found"
        assert resp.headers["Content-Type"] == "text/plain"
        assert resp.url == "https://example.test/missing"

    def test_json(self) -> None:
        resp = FakeResponse(json_data={"key": "value"})
        assert resp.json() == {"key": "value"}

    def test_text_from_content(self) -> None:
        resp = FakeResponse(content=b"hello")
        assert resp.text == "hello"

    def test_text_explicit(self) -> None:
        resp = FakeResponse(text="explicit text")
        assert resp.text == "explicit text"


class TestHttpOk:
    def test_default_is_ok(self) -> None:
        result = http_ok()
        assert result.is_ok
        assert result.err is None
        assert result.response is not None
        assert result.response.status_code == 200

    def test_error_status_still_ok(self) -> None:
        """HttpResult con response 404 e' is_ok (response presente)."""
        result = http_ok(404, b"not found")
        assert result.is_ok
        assert result.response.status_code == 404

    def test_json_data(self) -> None:
        result = http_ok(json_data={"data": [1, 2, 3]})
        assert result.response is not None
        assert result.response.json() == {"data": [1, 2, 3]}

    def test_headers(self) -> None:
        result = http_ok(headers={"Retry-After": "30"})
        assert result.response is not None
        assert result.response.headers["Retry-After"] == "30"


class TestHttpError:
    def test_generic_exception(self) -> None:
        result = http_error(ConnectionError("refused"))
        assert result.is_error
        assert "refused" in str(result.err)

    def test_default_error(self) -> None:
        result = http_error()
        assert result.is_error
        assert str(result.err) == "unknown error"

    def test_ssl_fallback_error(self) -> None:
        result = http_error(
            primary=Exception("SSL failed"),
            fallback=ConnectionError("fallback also failed"),
        )
        assert result.is_error
        assert isinstance(result.err, HttpFallbackError)
        assert "Exception" in str(result.err)
        assert "ConnectionError" in str(result.err)

    def test_mutual_exclusive_raises(self) -> None:
        with pytest.raises(ValueError, match="entrambi"):
            http_error(
                exc=ConnectionError("no"),
                primary=Exception("also no"),
            )
