from __future__ import annotations

from typing import Any

# ── Lazy imports ──────────────────────────────────────────────────────────────
# http (requests) and mcp (FastMCP SDK) are expensive to import (~3.5s each).
# We defer them so that `import lab_connectors.duckdb` stays fast.
# Names are resolved on first access (Python >= 3.7 __getattr__).
#
# Usage: `from lab_connectors import HttpClient`  # resolves lazily

_LAZY_SUBMODULES: dict[str, str] = {
    # lab_connectors.http
    "CircuitOpenError": "lab_connectors.http",
    "GenericPool": "lab_connectors.http",
    "HttpClient": "lab_connectors.http",
    "HttpFallbackError": "lab_connectors.http",
    "HttpResult": "lab_connectors.http",
    # lab_connectors.mcp
    "CacheStats": "lab_connectors.mcp",
    "ErrorCode": "lab_connectors.mcp",
    "McpError": "lab_connectors.mcp",
    "McpLogger": "lab_connectors.mcp",
    "TtlCache": "lab_connectors.mcp",
    "create_mcp_server": "lab_connectors.mcp",
    "get_mcp_logger": "lab_connectors.mcp",
    "guard": "lab_connectors.mcp",
    "guard_timed": "lab_connectors.mcp",
}


def __getattr__(name: str) -> Any:
    """Resolve names lazily when first accessed (PEP 562)."""
    if name in _LAZY_SUBMODULES:
        import importlib

        module = importlib.import_module(_LAZY_SUBMODULES[name])
        result = getattr(module, name)
        # Cache for subsequent accesses
        globals()[name] = result
        return result
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = list(_LAZY_SUBMODULES.keys())
