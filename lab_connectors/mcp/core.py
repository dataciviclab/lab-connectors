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
        return guard(_impl, config_path)

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

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover
    FastMCP = None  # type: ignore[assignment,misc]


def create_mcp_server(
    name: str,
    instructions: str,
    log_level: str = "INFO",
) -> FastMCP:
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
    if FastMCP is None:
        raise RuntimeError(
            "Il pacchetto 'mcp' non è installato. "
            "Installalo con: pip install lab-connectors[mcp]"
        )

    # Attiva logging strutturato
    get_mcp_logger(name, level=log_level)

    return FastMCP(name=name, instructions=instructions)


Fn = Callable[..., Any]


def guard(fn: Fn, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Avvolge una chiamata con try/except per tool MCP.

    Cattura ``McpError`` → restituisce ``{"error": code, "message": ...}``.
    Cattura eccezioni generiche → le avvolge con ``ErrorCode.UNEXPECTED``.

    Uso::

        @mcp.tool(description="...", structured_output=True)
        def my_tool(x: str) -> dict:
            return guard(_implementation, x)

    Returns:
        Dict con risultato in caso di successo, o dict con ``error``/``message``.

    """
    try:
        result = fn(*args, **kwargs)
        return result if isinstance(result, dict) else {"result": result}
    except McpError as exc:
        return exc.to_dict()
    except Exception as exc:
        return McpError.from_exception(exc).to_dict()


def guard_timed(
    fn: Fn,
    tool_name: str,
    *args: Any,
    logger_name: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Come ``guard()`` ma con logging strutturato della durata.

    Args:
        fn: Funzione da eseguire.
        tool_name: Nome del tool MCP (per logging).
        logger_name: Nome del server MCP (per logging). Default: same as tool_name.
        *args: Args posizionali passati a fn.
        **kwargs: Args keyword passati a fn.

    Returns:
        Dict con risultato o errore.

    """
    # logger_name dovrebbe essere il nome del server, non del tool.
    # Se non passato, usa il tool_name come fallback ma avvisa via log.
    _log_name = logger_name or tool_name
    logger = get_mcp_logger(_log_name)
    start = time.monotonic()

    try:
        result = fn(*args, **kwargs)
        elapsed = round((time.monotonic() - start) * 1000)
        logger.info(tool_name, f"OK ({elapsed}ms)", duration_ms=elapsed)
        return result if isinstance(result, dict) else {"result": result}
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
        logger.error(
            tool_name,
            f"Errore inaspettato: {mcp_err.code.value} ({elapsed}ms)",
            error_code=mcp_err.code.value,
            duration_ms=elapsed,
            exc_info=True,
        )
        return mcp_err.to_dict()
