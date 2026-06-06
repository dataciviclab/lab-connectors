from __future__ import annotations

from lab_connectors.http.client import HttpClient
from lab_connectors.http.sparql import (
    discover_graphs,
    execute_sparql,
    fetch_csv,
    infer_schema,
)
from lab_connectors.http.types import HttpFallbackError, HttpResult

__all__ = [
    "HttpClient",
    "HttpFallbackError",
    "HttpResult",
    "execute_sparql",
    "fetch_csv",
    "discover_graphs",
    "infer_schema",
]
