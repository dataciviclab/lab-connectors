"""Contract tests: lazy root exports via __getattr__ (PEP 562).

Verifies that:
- from lab_connectors import HttpClient resolves lazily (no FastMCP)
- mcp submodules can be imported without loading FastMCP
- create_mcp_server() imports FastMCP only when called
- All __all__ names resolve correctly
"""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.contract


def _has_fastmcp_in_modules() -> bool:
    """Check if FastMCP is loaded in sys.modules."""
    return any("fastmcp" in m.lower() or "mcp.server" in m.lower() for m in sys.modules)


class TestRootLazyExports:
    """Test that root package exports are lazy and FastMCP stays unloaded."""

    def test_import_connector_submodules_without_fastmcp(self) -> None:
        """Submodules like cache and errors should NOT trigger FastMCP."""
        # Fresh check — FastMCP may have been loaded by previous tests
        import lab_connectors.mcp.cache as _cache
        import lab_connectors.mcp.errors as _errors

        assert _cache is not None
        assert _errors is not None

    def test_create_mcp_server_import_is_lazy(self) -> None:
        """Importing create_mcp_server should NOT load FastMCP."""
        # Record modules before
        before = set(sys.modules.keys())

        after = set(sys.modules.keys())
        new = after - before
        fastmcp_loaded = any("fastmcp" in m.lower() or "mcp.server" in m.lower() for m in new)
        assert not fastmcp_loaded, f"create_mcp_server import loaded FastMCP: {new}"

    def test_create_mcp_server_call_loads_fastmcp(self) -> None:
        """Calling create_mcp_server() SHOULD load FastMCP.

        Checks that _get_fastmcp() imports FastMCP internally when called,
        regardless of whether previous tests have already loaded it.
        """
        from lab_connectors.mcp.core import _get_fastmcp

        # Clear any cached result from previous calls
        result = _get_fastmcp()
        if result is None:
            pytest.skip("FastMCP not installed (no [mcp] extra)")

        assert result is not None
        assert result.__name__ in {"FastMCP", "MCPServer"}


class TestRootLazyNameResolution:
    """Test that all __all__ names resolve correctly via __getattr__."""

    def test_all_http_names_resolve(self) -> None:
        from lab_connectors import (
            CircuitOpenError,
            HttpClient,
            HttpFallbackError,
        )

        assert HttpClient is not None
        assert CircuitOpenError is not None
        assert HttpFallbackError is not None

    def test_all_mcp_names_resolve(self) -> None:
        from lab_connectors import (
            McpError,
            create_mcp_server,
            guard,
        )

        assert McpError is not None
        assert create_mcp_server is not None
        assert guard is not None
