"""Context manager ``safe_connect`` per connessioni DuckDB.

Elimina il pattern ``duckdb.connect()`` + ``try/finally`` + ``con.close()``
duplicato in 3+ repo del Lab.

Uso tipico::

    from lab_connectors.duckdb import safe_connect

    with safe_connect(":memory:", tool_name="my_tool") as con:
        result = con.execute("SELECT 1").fetchall()

Se ``mcp`` è installato (extra ``[mcp]``), gli errori DuckDB vengono avvolti
in ``McpError`` con codice ``ErrorCode.DUCKDB_ERROR`` e il logging usa
``McpLogger`` strutturato. Se ``mcp`` non è installato, le eccezioni
originali propagano e il logging usa ``logging.getLogger`` standard.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger("lab_connectors.duckdb")

# ---------------------------------------------------------------------------
# Optional: McpLogger / McpError (solo se extra [mcp] è installato)
# ---------------------------------------------------------------------------

_MCP_LOGGER: Any | None = None
_MCP_ERROR: type | None = None
_ERROR_CODE_DUCKDB: Any = None


def _try_load_mcp() -> None:
    """Tenta di caricare McpLogger, McpError, ErrorCode da lab_connectors.mcp.

    Silenzioso se mcp non è installato o se l'import fallisce.
    """
    global _MCP_LOGGER, _MCP_ERROR, _ERROR_CODE_DUCKDB
    if _MCP_LOGGER is not None:
        return  # già tentato

    try:
        from lab_connectors.mcp.errors import ErrorCode, McpError

        _MCP_ERROR = McpError
        _ERROR_CODE_DUCKDB = ErrorCode.DUCKDB_ERROR
    except ImportError:
        pass

    try:
        from lab_connectors.mcp.logging import get_mcp_logger

        _MCP_LOGGER = get_mcp_logger
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@contextmanager
def safe_connect(
    database: str = ":memory:",
    *,
    tool_name: str | None = None,
    read_only: bool = False,
) -> Generator[Any, None, None]:
    """Context manager per connessioni DuckDB.

    Args:
        database: Path al database o ``":memory:"`` (default).
                  ``read_only=True`` non è supportato su ``:memory:``.
        tool_name: Nome del tool MCP (per logging strutturato).
                  Se ``None``, logga solo via stdlib.
        read_only: Apre il database in modalità read-only.
                  Funziona solo su database su file.

    Yields:
        duckdb.DuckDBPyConnection — connessione aperta.

    Raises:
        McpError(DUCKDB_ERROR): Se mcp è installato e DuckDB solleva eccezioni.
        duckdb.Error: Se mcp non è installato (eccezione originale).

    """
    _try_load_mcp()

    import duckdb  # import ritardato: duckdb è extra opzionale

    _log_open(database, tool_name)
    start = time.monotonic()

    try:
        con = duckdb.connect(database, read_only=read_only)
    except Exception as exc:
        _log_fail(exc, tool_name, start)
        raise _wrap_error(exc, f"Impossibile aprire connessione DuckDB: {exc}") from exc

    try:
        yield con

    except Exception as exc:
        _log_fail(exc, tool_name, start)
        raise _wrap_error(exc, f"Errore DuckDB: {exc}") from exc

    else:
        _log_ok(database, tool_name, start)

    finally:
        try:
            con.close()
        except Exception:
            pass  # cleanup silenzioso


# ---------------------------------------------------------------------------
# Helpers interni
# ---------------------------------------------------------------------------


def _wrap_error(exc: Exception, message: str) -> Exception:
    """Avvolge in McpError se disponibile, altrimenti restituisce l'originale."""
    if _MCP_ERROR is not None and _ERROR_CODE_DUCKDB is not None:
        return _MCP_ERROR(code=_ERROR_CODE_DUCKDB, message=message)
    return exc


def _log_open(database: str, tool_name: str | None) -> None:
    """Logga apertura connessione."""
    if tool_name and _MCP_LOGGER:
        mcp_logger = _MCP_LOGGER(tool_name)
        mcp_logger.info(tool_name, f"DuckDB open: {database}")
    else:
        logger.info("DuckDB open: %s", database)


def _log_ok(database: str, tool_name: str | None, start: float) -> None:
    """Logga chiusura connessione con durata."""
    elapsed_ms = round((time.monotonic() - start) * 1000)
    if tool_name and _MCP_LOGGER:
        mcp_logger = _MCP_LOGGER(tool_name)
        mcp_logger.info(tool_name, f"DuckDB OK ({elapsed_ms}ms)", duration_ms=elapsed_ms)
    else:
        logger.info("DuckDB OK (%dms)", elapsed_ms)


def _log_fail(exc: Exception, tool_name: str | None, start: float) -> None:
    """Logga errore con durata."""
    elapsed_ms = round((time.monotonic() - start) * 1000)
    if tool_name and _MCP_LOGGER:
        mcp_logger = _MCP_LOGGER(tool_name)
        mcp_logger.error(
            tool_name,
            f"DuckDB error ({elapsed_ms}ms)",
            duration_ms=elapsed_ms,
            error=str(exc),
        )
    else:
        logger.error("DuckDB error (%dms): %s", elapsed_ms, exc)
