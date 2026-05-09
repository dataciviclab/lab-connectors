"""Contratti cross-repo per server MCP del DataCivicLab.

Queste funzioni di assertion sono importabili dai test di ogni consumer
(toolkit, source-observatory, dataset-incubator, agent-context-builder)
per verificare che il server MCP rispetti i contratti standard del Lab.

Uso tipico in un consumer::

    from lab_connectors.mcp.contracts import (
        assert_valid_error_shape,
        assert_server_init,
        assert_error_code_taxonomy,
    )

    assert_server_init(mcp, "toolkit")
    assert_valid_error_shape(guard(lambda: 1/0))
"""

from __future__ import annotations

from typing import Any

from lab_connectors.mcp.errors import ErrorCode


# ── Cross-repo test markers ─────────────────────────────────────────────────
# Questi marker sono registrati in pyproject.toml di ogni repo del Lab.
# Documentazione: lab-ops/operations/test-policy.md

CROSS_REPO_MARKERS: dict[str, str] = {
    "contract": "public API, artifact format, CLI stable output",
    "regression": "documented bug fix (requires issue/PR link in docstring)",
    "pure_unit": "non-trivial pure logic (no side effects)",
    "smoke": "end-to-end golden-path smoke only",
}
"""Marker pytest validi in tutti i repo del DataCivicLab.

Ogni repo DEVE registrarli nel proprio pyproject.toml o pytest.ini.
Puo aggiungere marker repo-specifici oltre a questi.
"""


# ── Init pattern ────────────────────────────────────────────────────────────


def assert_server_init(mcp: Any, expected_name: str) -> None:
    """Verifica che il server sia stato creato con create_mcp_server()."""
    assert mcp is not None, "mcp non deve essere None"
    assert mcp.name == expected_name, (
        f"mcp.name={mcp.name!r}, atteso {expected_name!r}"
    )
    assert type(mcp).__name__ == "FastMCP", (
        f"tipo mcp={type(mcp).__name__}, atteso FastMCP"
    )


def assert_tools_registered(mcp: Any, min_tools: int = 1) -> set[str]:
    """Verifica che il server abbia almeno min_tools tool registrati.

    Returns:
        Set dei nomi dei tool registrati.
    """
    tools = set()
    for t in mcp._tool_manager._tools:
        tools.add(t if isinstance(t, str) else t.name)
    assert len(tools) >= min_tools, (
        f"tool registrati: {len(tools)}, attesi almeno {min_tools}: {tools}"
    )
    return tools


# ── Error shape ─────────────────────────────────────────────────────────────


def assert_valid_error_shape(result: dict[str, Any]) -> None:
    """Verifica che un dict di errore MCP abbia error + message.

    Esempi validi::

        {"error": "artifact_not_found", "message": "File non trovato"}
        {"error": "unexpected_error", "message": "division by zero"}
    """
    assert isinstance(result, dict), f"Risultato non e un dict: {type(result)}"
    assert "error" in result, f"Chiave 'error' mancante in: {result}"
    assert "message" in result, f"Chiave 'message' mancante in: {result}"
    assert isinstance(result["error"], str), (
        f"error non e str: {type(result['error'])}"
    )
    assert isinstance(result["message"], str), (
        f"message non e str: {type(result['message'])}"
    )
    assert result["error"], f"error e vuoto: {result}"
    assert result["message"], f"message e vuoto: {result}"


def assert_error_code_taxonomy(result: dict[str, Any]) -> None:
    """Verifica che l'error code sia un valore valido di ErrorCode."""
    assert_valid_error_shape(result)
    valid_codes = {c.value for c in ErrorCode}
    assert result["error"] in valid_codes, (
        f"error code '{result['error']}' non valido. "
        f"Usa uno tra: {sorted(valid_codes)}"
    )


# ── Guard pattern ───────────────────────────────────────────────────────────


def assert_guard_error(
    fn, *args: Any, **kwargs: Any
) -> dict[str, Any]:
    """Chiama fn tramite guard() e verifica errore strutturato.

    Returns:
        Il dict di errore restituito da guard().
    """
    from lab_connectors.mcp import guard as lc_guard

    result = lc_guard(fn, *args, **kwargs)
    assert_valid_error_shape(result)
    return result


def assert_success_shape(result: dict[str, Any]) -> None:
    """Verifica che un risultato di successo non contenga 'error'."""
    assert isinstance(result, dict), (
        f"Risultato non e un dict: {type(result)}"
    )
    assert "error" not in result, (
        f"Risultato contiene 'error', ma expected success: {result}"
    )


def assert_guard_behavior(
    fn_success, fn_error, *args, **kwargs
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Test completo del pattern guard: successo e errore.

    Returns:
        (success_result, error_result)
    """
    from lab_connectors.mcp import guard as lc_guard

    success = lc_guard(fn_success, *args, **kwargs)
    assert_success_shape(success)

    error = lc_guard(fn_error, *args, **kwargs)
    assert_valid_error_shape(error)

    return success, error
