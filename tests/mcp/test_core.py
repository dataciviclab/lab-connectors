"""Tests per lab_connectors.mcp.core."""
from __future__ import annotations

from lab_connectors.mcp.core import guard, guard_timed
from lab_connectors.mcp.errors import ErrorCode, McpError


class TestGuard:
    def test_guard_success_returns_dict(self) -> None:
        result = guard(lambda: {"ok": True})
        assert result == {"ok": True}

    def test_guard_wraps_non_dict_result(self) -> None:
        result = guard(lambda: "string_result")
        assert result == {"result": "string_result"}

    def test_guard_catches_mcp_error(self) -> None:
        def _fail() -> None:
            raise McpError(ErrorCode.ARTIFACT_NOT_FOUND, "Non trovato")

        result = guard(_fail)
        assert result == {"error": "artifact_not_found", "message": "Non trovato"}

    def test_guard_catches_generic_exception(self) -> None:
        def _fail() -> None:
            raise ValueError("qualcosa è andato storto")

        result = guard(_fail)
        assert result["error"] == "unexpected_error"
        assert "qualcosa è andato storto" in result["message"]

    def test_guard_passes_args(self) -> None:
        result = guard(lambda a, b: {"sum": a + b}, 3, 4)
        assert result == {"sum": 7}

    def test_guard_passes_kwargs(self) -> None:
        result = guard(lambda x, y=1: {"product": x * y}, 5, y=3)
        assert result == {"product": 15}


class TestGuardTimed:
    def test_success_logs_and_returns(self) -> None:
        result = guard_timed(lambda: {"ok": True}, "test_tool", logger_name="test-guard-timed")
        assert result == {"ok": True}

    def test_error_logs_and_returns_error_dict(self) -> None:
        def _fail() -> None:
            raise McpError(ErrorCode.INVALID_PARAMS, "male")

        result = guard_timed(_fail, "test_tool_err", logger_name="test-guard-timed")
        assert result == {"error": "invalid_params", "message": "male"}

    def test_unexpected_error_logs_and_returns(self) -> None:
        def _fail() -> None:
            raise RuntimeError("unexpected")

        result = guard_timed(_fail, "test_tool_unexpected", logger_name="test-guard-timed")
        assert result["error"] == "unexpected_error"
