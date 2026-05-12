"""Context manager per connessioni DuckDB.

Uso::

    from lab_connectors.duckdb import safe_connect

    with safe_connect("path/to/db.duckdb") as con:
        rows = con.execute("SELECT 1").fetchall()
"""

from __future__ import annotations

from lab_connectors.duckdb.core import safe_connect

__all__ = ["safe_connect"]
