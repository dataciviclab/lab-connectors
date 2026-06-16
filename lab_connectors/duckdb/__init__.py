"""Context manager per connessioni DuckDB.

Uso::

    from lab_connectors.duckdb import gcs_connect, safe_connect

    # Connessione base
    with safe_connect() as con:
        rows = con.execute("SELECT 1").fetchall()

    # Lettura da GCS pubblico via HTTPS (stabile, senza estensioni)
    with gcs_connect("https://storage.googleapis.com/dataciviclab-clean/...") as con:
        con.execute("SELECT * FROM read_parquet('https://storage.googleapis.com/...')")

    # Legacy: path S3 con httpfs
    # with safe_connect(extensions=["httpfs"], config=GCS_S3_CONFIG) as con:
    #     con.execute("SELECT * FROM read_parquet('s3://bucket/file.parquet')")
"""

from __future__ import annotations

from lab_connectors.duckdb.core import GCS_S3_CONFIG, gcs_connect, safe_connect

__all__ = ["GCS_S3_CONFIG", "gcs_connect", "safe_connect"]
