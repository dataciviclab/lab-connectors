"""Tassonomia unificata degli errori MCP per DataCivicLab.

Ogni errore ha un codice macchina (ErrorCode) e un messaggio umano.
I codici sono categorizzati per dominio: artifact, config, gcs, query, cache, generic.
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    """Codici errore tassonomici per MCP.

    Pattern: `<dominio>_<problema>` in snake_case.
    """

    # — Artifact resolution —
    ARTIFACT_NOT_FOUND = "artifact_not_found"
    ARTIFACT_STALE = "artifact_stale"
    ARTIFACT_UNREADABLE = "artifact_unreadable"
    PARQUET_NOT_FOUND = "parquet_not_found"
    JSON_NOT_FOUND = "json_not_found"

    # — Configuration —
    CONFIG_NOT_FOUND = "config_not_found"
    CONFIG_INVALID = "config_invalid"
    CONFIG_MALFORMED = "config_malformed"

    # — GCS / remote storage —
    GCS_UNAVAILABLE = "gcs_unavailable"
    GCS_TIMEOUT = "gcs_timeout"
    GCS_AUTH_ERROR = "gcs_auth_error"

    # — DuckDB / query —
    QUERY_ERROR = "query_error"
    QUERY_TIMEOUT = "query_timeout"
    QUERY_SCOPE_VIOLATION = "query_scope_violation"
    DUCKDB_ERROR = "duckdb_error"

    # — Cache —
    CACHE_STALE = "cache_stale"
    CACHE_MISS = "cache_miss"

    # — Parameters —
    INVALID_PARAMS = "invalid_params"
    EMPTY_PARAM = "empty_param"
    SLUG_NOT_FOUND = "slug_not_found"

    # — Generic —
    UNEXPECTED = "unexpected_error"
    NOT_IMPLEMENTED = "not_implemented"


class McpError(RuntimeError):
    """Eccezione base per tutti gli errori MCP del Lab.

    Trasporta un codice macchina (ErrorCode) e un messaggio umano.
    Usata da `guard()` per produrre risposte JSON strutturate.
    """

    def __init__(self, code: ErrorCode, message: str) -> None:
        """Inizializza l'errore con codice e messaggio."""
        self.code = code
        self.message = message
        super().__init__(f"[{code.value}] {message}")

    def to_dict(self) -> dict[str, str]:
        """Convert in dict per risposte JSON strutturate."""
        return {"error": self.code.value, "message": self.message}

    @classmethod
    def from_exception(
        cls, exc: Exception, fallback_code: ErrorCode = ErrorCode.UNEXPECTED
    ) -> McpError:
        """Avvolge un'eccezione generica in McpError."""
        if isinstance(exc, McpError):
            return exc
        return cls(code=fallback_code, message=str(exc))
