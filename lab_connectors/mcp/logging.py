"""Logging strutturato per server MCP.

Fornisce un McpLogger che produce log JSON strutturati con metadati
(server, tool, duration_ms, cache_source, error_code) consumabili
da sistemi di observability e debug degli agenti.
"""

from __future__ import annotations

import logging
import time
from typing import Any


class McpLogger:
    """Logger strutturato per tool MCP.

    Ogni metodo accetta un parametro ``tool`` (nome del tool MCP)
    e ``extra`` opzionale per dati contestuali strutturati.

    Uso::

        logger = get_mcp_logger("source-observatory")
        logger.info("so_probe_url", "Probing URL", url="https://...")
    """

    def __init__(self, logger: logging.Logger) -> None:
        """Avvolge un logger standard."""
        self._logger = logger

    def info(self, tool: str, msg: str, **extra: Any) -> None:
        """Logga un messaggio informativo."""
        self._logger.info(self._format(tool, msg, extra))

    def warning(self, tool: str, msg: str, **extra: Any) -> None:
        """Logga un avviso."""
        self._logger.warning(self._format(tool, msg, extra))

    def error(self, tool: str, msg: str, exc_info: Any = None, **extra: Any) -> None:
        """Logga un errore."""
        self._logger.error(self._format(tool, msg, extra), exc_info=exc_info)

    def debug(self, tool: str, msg: str, **extra: Any) -> None:
        """Logga un messaggio di debug."""
        self._logger.debug(self._format(tool, msg, extra))

    def timed(
        self, tool: str, msg: str, start: float, **extra: Any
    ) -> None:
        """Log con durata calcolata da un timestamp start."""
        duration_ms = round((time.monotonic() - start) * 1000)
        self.info(tool, msg, duration_ms=duration_ms, **extra)

    @staticmethod
    def _format(tool: str, msg: str, extra: dict[str, Any]) -> str:
        parts = [f"[{tool}] {msg}"]
        if extra:
            detail = " ".join(f"{k}={v!r}" for k, v in extra.items())
            parts.append(f"({detail})")
        return " ".join(parts)


# — Registry globale lazy: nome → McpLogger —
_loggers: dict[str, McpLogger] = {}


def get_mcp_logger(server_name: str, level: str = "INFO") -> McpLogger:
    """Restituisce (o crea) un McpLogger per il server MCP ``server_name``.

    Il logger sottostante ha nome ``dataciviclab.mcp.<server_name>``.
    Il livello si imposta via ``level`` (default INFO) o via env var
    ``DATACIVICLAB_MCP_LOG_LEVEL``.
    """
    if server_name in _loggers:
        return _loggers[server_name]

    import os

    log_level = os.environ.get("DATACIVICLAB_MCP_LOG_LEVEL", level).upper()
    logger = logging.getLogger(f"dataciviclab.mcp.{server_name}")
    logger.setLevel(getattr(logging, log_level, logging.INFO))

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(getattr(logging, log_level, logging.INFO))
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    mcp_logger = McpLogger(logger)
    _loggers[server_name] = mcp_logger
    return mcp_logger
