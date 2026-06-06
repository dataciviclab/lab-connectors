"""Context manager ``safe_connect`` per connessioni DuckDB.

Elimina il pattern ``duckdb.connect()`` + ``try/finally`` + ``con.close()``
duplicato in 3+ repo del Lab.

Supporta estensioni (es. ``httpfs`` per GCS) e configurazione DuckDB.

Uso::

    from lab_connectors.duckdb import safe_connect

    with safe_connect() as con:
        result = con.execute("SELECT 1").fetchall()

    with safe_connect(extensions=["httpfs"]) as con:
        con.execute("SELECT * FROM read_parquet('s3://bucket/file.parquet')")

    with safe_connect(config={"s3_region": "auto"}) as con:
        con.execute("SELECT * FROM read_parquet('s3://bucket/file.parquet')")
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any


@contextmanager
def safe_connect(
    database: str = ":memory:",
    extensions: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> Generator[Any, None, None]:
    """Context manager per connessioni DuckDB.

    Args:
        database: Path al database o ``":memory:"`` (default).
        extensions: Lista di estensioni DuckDB da caricare (es. ``["httpfs"]``).
        config: Dict di configurazione DuckDB (es. ``{"s3_region": "auto"}``).

    Yields:
        duckdb.DuckDBPyConnection — connessione aperta.

    Raises:
        duckdb.Error: eccezione originale DuckDB, nessun wrapping.

    """
    import duckdb  # duckdb è extra opzionale [duckdb]

    con = duckdb.connect(database, config=config or {})
    try:
        if extensions:
            for ext in extensions:
                con.execute(f"LOAD {ext}")
        yield con
    finally:
        try:
            con.close()
        except Exception:
            pass
