from __future__ import annotations

from lab_connectors.http.client import HttpClient
from lab_connectors.http.download import download
from lab_connectors.http.sparql import (
    curl_sparql,
    discover_graphs,
    execute_sparql,
    execute_sparql_rows,
    execute_sparql_rows_curl,
    fetch_csv,
    infer_schema,
)
from lab_connectors.http.types import CircuitOpenError, HttpFallbackError, HttpResult

__all__ = [
    "CircuitOpenError",
    "HttpClient",
    "HttpFallbackError",
    "HttpResult",
    "curl_sparql",
    "discover_graphs",
    "download",
    "execute_sparql",
    "execute_sparql_rows",
    "execute_sparql_rows_curl",
    "fetch_csv",
    "infer_schema",
]
