"""Context manager ``safe_connect`` per connessioni DuckDB.

Elimina il pattern ``duckdb.connect()`` + ``try/finally`` + ``con.close()``
duplicato in 3+ repo del Lab.

Uso::

    from lab_connectors.duckdb import safe_connect

    with safe_connect(":memory:") as con:
        result = con.execute("SELECT 1").fetchall()
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any


@contextmanager
def safe_connect(
    database: str = ":memory:",
) -> Generator[Any, None, None]:
    """Context manager per connessioni DuckDB.

    Args:
        database: Path al database o ``":memory:"`` (default).

    Yields:
        duckdb.DuckDBPyConnection — connessione aperta.

    Raises:
        duckdb.Error: eccezione originale DuckDB, nessun wrapping.

    """
    import duckdb  # duckdb è extra opzionale [duckdb]

    con = duckdb.connect(database)
    try:
        yield con
    finally:
        try:
            con.close()
        except Exception:
            pass
