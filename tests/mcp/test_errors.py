"""Tests per lab_connectors.mcp.errors."""
from __future__ import annotations

import pytest

from lab_connectors.mcp.errors import ErrorCode, McpError

pytestmark = pytest.mark.pure_unit


class TestErrorCode:
    def test_values_are_snake_case(self) -> None:
        for code in ErrorCode:
            assert "_" in code.value, f"{code.value} non contiene underscore"
            assert code.value.islower(), f"{code.value} non è lowercase"

    def test_all_codes_unique(self) -> None:
        values = [c.value for c in ErrorCode]
        assert len(values) == len(set(values))


class TestMcpError:
    def test_basic_creation(self) -> None:
        err = McpError(ErrorCode.ARTIFACT_NOT_FOUND, "File non trovato")
        assert err.code == ErrorCode.ARTIFACT_NOT_FOUND
        assert err.message == "File non trovato"

    def test_str_contains_code_and_message(self) -> None:
        err = McpError(ErrorCode.GCS_UNAVAILABLE, "GCS non raggiungibile")
        s = str(err)
        assert "gcs_unavailable" in s
        assert "GCS non raggiungibile" in s

    def test_to_dict(self) -> None:
        err = McpError(ErrorCode.INVALID_PARAMS, "Parametro mancante")
        d = err.to_dict()
        assert d == {"error": "invalid_params", "message": "Parametro mancante"}

    def test_from_exception_preserves_mcp_error(self) -> None:
        original = McpError(ErrorCode.QUERY_TIMEOUT, "Timeout query")
        wrapped = McpError.from_exception(original)
        assert wrapped is original

    def test_from_exception_wraps_generic(self) -> None:
        original = ValueError("qualcosa è andato storto")
        wrapped = McpError.from_exception(original)
        assert isinstance(wrapped, McpError)
        assert wrapped.code == ErrorCode.UNEXPECTED
        assert "qualcosa è andato storto" in wrapped.message

    def test_from_exception_with_custom_fallback_code(self) -> None:
        original = RuntimeError("errore runtime")
        wrapped = McpError.from_exception(original, fallback_code=ErrorCode.QUERY_ERROR)
        assert wrapped.code == ErrorCode.QUERY_ERROR
