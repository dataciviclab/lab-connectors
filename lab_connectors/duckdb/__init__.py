"""Context manager per connessioni DuckDB.

Uso::

    from lab_connectors.duckdb import gcs_connect, safe_connect, GCS_S3_CONFIG

    with safe_connect("path/to/db.duckdb") as con:
        rows = con.execute("SELECT 1").fetchall()

    with safe_connect(extensions=["httpfs"], config=GCS_S3_CONFIG) as con:
        con.execute("SELECT * FROM read_parquet('s3://bucket/file.parquet')")

    with gcs_connect("s3://bucket/file.parquet") as con:
        con.execute("SELECT * FROM read_parquet('s3://bucket/file.parquet')")
"""

from __future__ import annotations

from lab_connectors.duckdb.core import GCS_S3_CONFIG, gcs_connect, safe_connect

__all__ = ["GCS_S3_CONFIG", "gcs_connect", "safe_connect"]
