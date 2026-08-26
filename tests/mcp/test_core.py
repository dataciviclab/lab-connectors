"""Tests per lab_connectors.mcp.core."""

from __future__ import annotations

import time

import pytest

from lab_connectors.mcp.core import DEFAULT_SLOW_MS, create_mcp_server, guard, guard_timed
from lab_connectors.mcp.errors import ErrorCode, McpError

pytestmark = pytest.mark.contract


class TestCreateMcpServer:
    def test_creates_fastmcp_with_name(self) -> None:
        """create_mcp_server deve restituire un FastMCP/MCPServer con nome corretto."""
        mcp = create_mcp_server("test-server", "Test instructions")
        assert mcp.name == "test-server"
        # v1.x: FastMCP, v2.x: MCPServer
        assert type(mcp).__name__ in ("FastMCP", "MCPServer")

    def test_creates_fastmcp_with_instructions(self) -> None:
        """Le instructions devono essere accessibili."""
        mcp = create_mcp_server("test", "Istruzioni di test")
        assert "Istruzioni di test" in mcp.instructions

    def test_fastmcp_tools_can_be_registered(self) -> None:
        """Il server deve supportare la registrazione di strumenti."""
        mcp = create_mcp_server("test-tools", "Test tools")

        @mcp.tool(description="test tool")
        def my_tool(x: int) -> str:
            return str(x * 2)

        tools = {t if isinstance(t, str) else t.name for t in mcp._tool_manager._tools}
        assert "my_tool" in tools


class TestGuard:
    def test_guard_success_returns_dict(self) -> None:
        result = guard(lambda: {"ok": True})
        assert result == {"ok": True}

    def test_guard_passes_non_dict_result(self) -> None:
        result = guard(lambda: "string_result")
        assert result == "string_result"  # non wrappa più in {"result": ...}

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

    def test_default_logger_name(self) -> None:
        """Deve funzionare anche senza logger_name (default = tool_name)."""
        result = guard_timed(lambda: {"ok": True}, "test_tool_default")
        assert result == {"ok": True}

    def test_slow_ms_default(self) -> None:
        """slow_ms di default (5000) non altera il risultato."""
        result = guard_timed(lambda: {"ok": True}, "test_tool", logger_name="test")
        assert result == {"ok": True}

    def test_slow_ms_zero(self) -> None:
        """slow_ms=0 funziona (tutte le chiamate oltre soglia)."""
        result = guard_timed(lambda: {"ok": True}, "test_tool", slow_ms=0, logger_name="test")
        assert result == {"ok": True}

    def test_slow_does_not_block_result(self) -> None:
        """Anche se la chiamata supera slow_ms, il risultato torna corretto."""

        def _slow() -> dict:
            time.sleep(0.015)  # 15ms
            return {"ok": "slow_but_ok"}

        result = guard_timed(_slow, "slow_tool", slow_ms=1, logger_name="test")
        assert result == {"ok": "slow_but_ok"}

    def test_slow_ms_constant_exists(self) -> None:
        """DEFAULT_SLOW_MS deve essere 5000."""
        assert DEFAULT_SLOW_MS == 5000
