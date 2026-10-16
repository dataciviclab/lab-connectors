"""Tests per lab_connectors.mcp.core — guard, guard_timed, factory.

Copre l'infrastruttura MCP condivisa (ex coperta anche dai test del
server github-discussions, rimossi con la migrazione a dcl-mcp).
"""

from __future__ import annotations

import logging

import pytest

from lab_connectors.mcp.core import DEFAULT_SLOW_MS, create_mcp_server, guard, guard_timed
from lab_connectors.mcp.errors import ErrorCode, McpError

pytestmark = pytest.mark.pure_unit


# ── create_mcp_server ─────────────────────────────────────────────────────────


class TestCreateMcpServer:
    def test_returns_named_server(self):
        mcp = create_mcp_server(name="test-server", instructions="test instructions")
        assert mcp.name == "test-server"

    def test_raises_without_mcp_package(self, monkeypatch):
        from lab_connectors.mcp import core

        monkeypatch.setattr(core, "_get_fastmcp", lambda: None)
        with pytest.raises(RuntimeError, match="non è installato"):
            create_mcp_server(name="x", instructions="y")


# ── guard ─────────────────────────────────────────────────────────────────────


class TestGuard:
    def test_success_passthrough(self):
        assert guard(lambda x: {"value": x}, 42) == {"value": 42}

    def test_mcp_error_to_dict(self):
        def boom() -> None:
            raise McpError(ErrorCode.CONFIG_NOT_FOUND, "manca la config")

        result = guard(boom)
        assert result == {"error": "config_not_found", "message": "manca la config"}

    def test_generic_exception_wrapped(self):
        def boom() -> None:
            raise ValueError("cacchio")

        result = guard(boom)
        assert result["error"] == ErrorCode.UNEXPECTED.value
        assert "cacchio" in result["message"]


# ── guard_timed ───────────────────────────────────────────────────────────────


class TestGuardTimed:
    def test_success_returns_result_and_logs_ok(self, caplog):
        caplog.set_level(logging.INFO)
        result = guard_timed(lambda: {"ok": True}, "my_tool")
        assert result == {"ok": True}
        assert "my_tool" in caplog.text
        assert "OK" in caplog.text

    def test_slow_call_logs_warning(self, caplog):
        caplog.set_level(logging.WARNING)
        guard_timed(lambda: "x", "slow_tool", slow_ms=-1)
        assert "slow=True" in caplog.text

    def test_default_slow_ms_constant(self):
        assert DEFAULT_SLOW_MS == 5000

    def test_mcp_error_logged_as_warning(self, caplog):
        caplog.set_level(logging.WARNING)

        def boom() -> None:
            raise McpError(ErrorCode.SLUG_NOT_FOUND, "slug inesistente")

        result = guard_timed(boom, "err_tool")
        assert result["error"] == "slug_not_found"
        assert "err_tool" in caplog.text

    def test_generic_exception_logged_as_error(self, caplog):
        caplog.set_level(logging.ERROR)

        def boom() -> None:
            raise RuntimeError("disastro")

        result = guard_timed(boom, "crash_tool")
        assert result["error"] == ErrorCode.UNEXPECTED.value
        assert "crash_tool" in caplog.text

    def test_args_kwargs_forwarded(self):
        def add(a: int, b: int = 0) -> dict[str, int]:
            return {"sum": a + b}

        assert guard_timed(add, "add_tool", 1, b=2) == {"sum": 3}
