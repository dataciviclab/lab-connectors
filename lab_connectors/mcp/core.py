"""Core MCP: factory per server standardizzati e pattern ``guard``.

Uso tipico in un server MCP::

    from lab_connectors.mcp import create_mcp_server, guard
    from lab_connectors.mcp.errors import McpError, ErrorCode

    mcp = create_mcp_server(
        name="toolkit",
        instructions="Read-only MCP per ispezione pipeline toolkit.",
    )

    @mcp.tool(description="...", structured_output=True)
    def toolkit_inspect_paths(config_path: str) -> dict:
        return guard_timed(_impl, "toolkit_inspect_paths", config_path)

    def _impl(config_path: str) -> dict:
        # ...
        if not path.exists():
            raise McpError(ErrorCode.CONFIG_NOT_FOUND, f"Config non trovata: {config_path}")
        return {"result": "..."}
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from lab_connectors.mcp.errors import McpError
from lab_connectors.mcp.logging import get_mcp_logger


def _get_fastmcp() -> type | None:
    """Lazy import of FastMCP (expensive: ~3.5s for pydantic+starlette)."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        FastMCP = None  # type: ignore[assignment, misc]
    return FastMCP


def create_mcp_server(
    name: str,
    instructions: str,
    log_level: str = "INFO",
) -> Any:
    """Crea un server FastMCP standardizzato per DataCivicLab.

    Configura automaticamente:
    - Nome e istruzioni (leggibili dall'agente AI)
    - Logger strutturato ``dataciviclab.mcp.<name>``
    - Health check implicito (nessuna configurazione extra)

    Args:
        name: Identificativo del server (es. ``"toolkit"``, ``"source-observatory"``).
        instructions: Testo descrittivo per l'agente AI cliente.
        log_level: Livello di logging (default ``INFO``).

    Returns:
        Istanza FastMCP configurata.

    Raises:
        RuntimeError: Se ``mcp`` non è installato.

    """
    fastmcp_cls = _get_fastmcp()
    if fastmcp_cls is None:
        raise RuntimeError(
            "Il pacchetto 'mcp' non è installato. Installalo con: pip install lab-connectors[mcp]"
        )

    # Attiva logging strutturato
    get_mcp_logger(name, level=log_level)

    return fastmcp_cls(name=name, instructions=instructions)


Fn = Callable[..., Any]


def guard(fn: Fn, *args: Any, **kwargs: Any) -> Any:
    """Avvolge una chiamata con try/except per tool MCP.

    Cattura ``McpError`` → restituisce ``{"error": code, "message": ...}``.
    Cattura eccezioni generiche → le avvolge con ``ErrorCode.UNEXPECTED``.

    Uso::

        @mcp.tool(description="...", structured_output=True)
        def my_tool(x: str) -> dict:
            return guard(_implementation, x)

    Returns:
        Il risultato di *fn* (dict, list, str...) — FastMCP serializza
        automaticamente. In caso di errore, dict con ``error``/``message``.

    """
    try:
        return fn(*args, **kwargs)
    except McpError as exc:
        return exc.to_dict()
    except Exception as exc:
        return McpError.from_exception(exc).to_dict()


DEFAULT_SLOW_MS = 5000


def _log_ok(logger: Any, tool_name: str, elapsed: int, slow_ms: int) -> None:
    """Logga esito OK, WARNING se oltre soglia."""
    if elapsed > slow_ms:
        logger.warning(
            tool_name,
            f"OK ({elapsed}ms)",
            duration_ms=elapsed,
            slow=True,
            threshold_ms=slow_ms,
        )
    else:
        logger.info(tool_name, f"OK ({elapsed}ms)", duration_ms=elapsed)


def guard_timed(
    fn: Fn,
    tool_name: str,
    *args: Any,
    logger_name: str | None = None,
    slow_ms: int = DEFAULT_SLOW_MS,
    **kwargs: Any,
) -> Any:
    """Come ``guard()`` ma con logging strutturato della durata.

    Logger e metriche di performance per ogni tool MCP.
    Il nome del logger si ricava automaticamente da *tool_name* se
    ``logger_name`` non è passato (tipicamente il nome del server).

    Se la chiamata supera *slow_ms* millisecondi, il log è WARNING
    invece di INFO con flag ``slow=True``.

    Args:
        fn: Funzione da eseguire.
        tool_name: Nome del tool MCP (usato come label nei log).
        logger_name: Nome del logger strutturato. Default: *tool_name*.
        slow_ms: Soglia lentezza in ms. Oltre, log WARNING. Default 5000.
        *args: Args posizionali passati a fn.
        **kwargs: Args keyword passati a fn.

    Returns:
        Dict con risultato o errore.

    """
    _log_name = logger_name or tool_name
    logger = get_mcp_logger(_log_name)
    start = time.monotonic()

    try:
        result = fn(*args, **kwargs)
        elapsed = round((time.monotonic() - start) * 1000)
        _log_ok(logger, tool_name, elapsed, slow_ms)
        return result
    except McpError as exc:
        elapsed = round((time.monotonic() - start) * 1000)
        logger.warning(
            tool_name,
            f"Errore: {exc.code.value} ({elapsed}ms)",
            error_code=exc.code.value,
            duration_ms=elapsed,
        )
        return exc.to_dict()
    except Exception as exc:
        elapsed = round((time.monotonic() - start) * 1000)
        mcp_err = McpError.from_exception(exc)
        logger.exception(
            tool_name,
            f"Errore inaspettato: {mcp_err.code.value} ({elapsed}ms)",
            error_code=mcp_err.code.value,
            duration_ms=elapsed,
        )
        return mcp_err.to_dict()
