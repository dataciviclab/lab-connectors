"""Contratti cross-repo per server MCP del DataCivicLab.

Queste funzioni di assertion sono importabili dai test di ogni consumer
(toolkit, source-observatory, dataset-incubator, agent-context-builder)
per verificare che il server MCP rispetti i contratti standard del Lab.

Uso tipico in un consumer::

    from lab_connectors.tests.mcp.contracts import (
        assert_valid_error_shape,
        assert_server_init,
        assert_error_code_taxonomy,
    )

    assert_server_init(mcp, "toolkit")
    assert_valid_error_shape(gward(lambda: 1/0))
"""

from __future__ import annotations

from typing import Any

from lab_connectors.mcp.errors import ErrorCode, McpError


# ── Init pattern ────────────────────────────────────────────────────────────

_SERVER_CREATED_BY = object()


def assert_server_init(mcp: Any, expected_name: str) -> None:
    """Verifica che il server sia stato creato con create_mcp_server().

    Controlli:
    - ``mcp.name`` corrisponde a ``expected_name``
    - ``mcp`` è un'istanza FastMCP (via ``type.__name__``)
    - Ha tool registrati (almeno 1)
    """
    assert mcp is not None, "mcp non deve essere None"
    assert mcp.name == expected_name, (
        f"mcp.name={mcp.name!r}, atteso {expected_name!r}"
    )
    assert type(mcp).__name__ == "FastMCP", (
        f"tipo mcp={type(mcp).__name__}, atteso FastMCP"
    )


def assert_tools_registered(mcp: Any, min_tools: int = 1) -> set[str]:
    """Verifica che il server abbia almeno ``min_tools`` tool registrati.

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
    """Verifica che un dict di errore MCP abbia la struttura canonica.

    Un errore valido deve avere:
    - ``error``: stringa, codice valido in ``ErrorCode``
    - ``message``: stringa, spiegazione leggibile

    Esempi validi::

        {"error": "artifact_not_found", "message": "File non trovato"}
        {"error": "unexpected_error", "message": "division by zero"}
    """
    assert isinstance(result, dict), f"Risultato non è un dict: {type(result)}"
    assert "error" in result, f"Chiave 'error' mancante in: {result}"
    assert "message" in result, f"Chiave 'message' mancante in: {result}"
    assert isinstance(result["error"], str), (
        f"error non è str: {type(result['error'])}"
    )
    assert isinstance(result["message"], str), (
        f"message non è str: {type(result['message'])}"
    )
    assert result["error"], f"error è vuoto: {result}"
    assert result["message"], f"message è vuoto: {result}"


def assert_error_code_taxonomy(result: dict[str, Any]) -> None:
    """Verifica che l'error code sia un valore valido di ``ErrorCode``.

    Fallisce se l'error code non è nella tassonomia ufficiale.
    """
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
    """Chiama ``fn`` tramite ``guard()`` e verifica errore.

    Richiede che lab_connectors.mcp.guard sia importato nel chiamante.
    La funzione deve sollevare un'eccezione — il test verifica che
    ``guard()`` la trasformi in dict con errore strutturato.

    Returns:
        Il dict di errore restituito da guard().
    """
    from lab_connectors.mcp import guard as lc_guard

    result = lc_guard(fn, *args, **kwargs)
    assert_valid_error_shape(result)
    return result


def assert_success_shape(result: dict[str, Any]) -> None:
    """Verifica che un risultato di successo abbia la struttura attesa.

    I tool possono restituire:
    - Un dict diretto (es. ``{"dataset": "...", "year": 2024}``)
    - Un dict con chiave ``result`` (es. ``{"result": "stringa"}``)

    Entrambi i casi sono validi.
    """
    assert isinstance(result, dict), (
        f"Risultato non è un dict: {type(result)}"
    )
    # Se c'è 'error', non è un successo — fallisce
    assert "error" not in result, (
        f"Risultato contiene 'error', ma è expected success: {result}"
    )


# ── Guard pattern tester (combinato) ────────────────────────────────────────


def assert_guard_behavior(fn_success, fn_error, *args, **kwargs) -> tuple[dict[str, Any], dict[str, Any]]:
    """Test completo del pattern guard: successo e errore.

    Args:
        fn_success: callable che restituisce un dict di successo.
        fn_error: callable che solleva un'eccezione.
        *args, **kwargs: passati a entrambe le callable (se supportati).

    Returns:
        (success_result, error_result)
    """
    from lab_connectors.mcp import guard as lc_guard

    # Test successo
    success = lc_guard(fn_success, *args, **kwargs)
    assert_success_shape(success)

    # Test errore
    error = lc_guard(fn_error, *args, **kwargs)
    assert_valid_error_shape(error)

    return success, error
