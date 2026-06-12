"""Context manager ``safe_connect`` per connessioni DuckDB.

Elimina il pattern ``duckdb.connect()`` + ``try/finally`` + ``con.close()``
duplicato in 3+ repo del Lab.

Supporta estensioni (es. ``httpfs`` per GCS) e configurazione DuckDB.
``safe_connect`` fa ``INSTALL`` + ``LOAD`` per ogni estensione,
quindi funziona anche su runner CI pulito.

Configurazioni di default applicate automaticamente (override via ``config``):
    - ``memory_limit``: ``'2GB'``
    - ``threads``: ``'4'``
    - ``PRAGMA disable_progress_bar``: sempre attivo

Estensione ``icu``: se inclusa in ``extensions``, safe_connect applica anche
``SET icu_collation='it-IT'`` dopo il caricamento.

Uso::

    from lab_connectors.duckdb import safe_connect, GCS_S3_CONFIG

    with safe_connect() as con:
        result = con.execute("SELECT 1").fetchall()

    # Estensione per GCS con config predefinita
    with safe_connect(extensions=["httpfs"]) as con:
        con.execute("SELECT * FROM read_parquet('s3://bucket/file.parquet')")

    # Config esplicita (sovrascrive i default parzialmente)
    with safe_connect(config=GCS_S3_CONFIG) as con:
        con.execute("SELECT * FROM read_parquet('s3://bucket/file.parquet')")

    # Collation italiana
    with safe_connect(extensions=["icu"]) as con:
        con.execute("SELECT * FROM read_parquet(...) ORDER BY città COLLATE it-IT")
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# ── Configurazione DuckDB per bucket GCS pubblici via S3-compatible API ───────
# Serve perche' DuckDB httpfs legge GCS tramite API S3, con endpoint
# storage.googleapis.com. Senza questa config, DuckDB prova AWS S3 e fallisce 404.

GCS_S3_CONFIG: dict[str, str] = {
    "s3_endpoint": "storage.googleapis.com",
    "s3_region": "auto",
    "s3_access_key_id": "",
    "s3_secret_access_key": "",
    "s3_use_ssl": "true",
}

# ── Configurazioni di default DuckDB per il Lab ──────────────────────────────
# Applicate da safe_connect se non sovrascritte dalla config esplicita.
# memory_limit: limite ragionevole per container/CI.
# threads: evita saturazione CPU su runner condivisi.

DEFAULT_CONFIG: dict[str, str] = {
    "memory_limit": "2GB",
    "threads": "4",
}


@contextmanager
def safe_connect(
    database: str = ":memory:",
    extensions: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> Generator[Any, None, None]:
    """Context manager per connessioni DuckDB.

    Applica automaticamente ``DEFAULT_CONFIG`` (memory_limit, threads)
    e ``PRAGMA disable_progress_bar``. I valori in ``config`` sovrascrivono
    i default.

    Se ``"icu"`` è in ``extensions``, applica anche ``SET icu_collation='it-IT'``
    dopo il caricamento.

    ``INSTALL`` + ``LOAD`` per ogni estensione specificata.
    ``INSTALL`` è idempotente — sicuro su runner con estensione già presente.

    Args:
        database: Path al database o ``":memory:"`` (default).
        extensions: Lista di estensioni DuckDB da installare e caricare
                    (es. ``["httpfs"]``, ``["httpfs", "icu"]``).
        config: Dict di configurazione DuckDB (es. ``GCS_S3_CONFIG``).
                I valori qui sovrascrivono ``DEFAULT_CONFIG``.

    Yields:
        duckdb.DuckDBPyConnection — connessione aperta.

    Raises:
        duckdb.Error: eccezione originale DuckDB, nessun wrapping.

    """
    import duckdb  # duckdb è extra opzionale [duckdb]

    # Merge: default + override esplicito
    merged_config: dict[str, Any] = {**DEFAULT_CONFIG, **(config or {})}

    con = duckdb.connect(database, config=merged_config)
    try:
        # Disabilita progress bar per output pulito (CLI, MCP, test)
        con.execute("PRAGMA disable_progress_bar")

        if extensions:
            for ext in extensions:
                con.execute(f"INSTALL {ext}")
                con.execute(f"LOAD {ext}")
                # Per l'estensione ICU, imposta collation italiana di default
                if ext == "icu":
                    con.execute("SET default_collation='it'")
        yield con
    finally:
        try:
            con.close()
        except Exception:
            pass


def _is_s3_path(path: str | Path) -> bool:
    """Indica se il path inizia con ``s3://`` (GCS via DuckDB httpfs).

    Rileva anche ``s3:/`` (``Path()`` normalizza ``//`` in ``/``).
    """
    s = str(path)
    return s.startswith("s3://") or s.startswith("s3:/")


@contextmanager
def gcs_connect(
    path: str | Path,
    database: str = ":memory:",
) -> Generator[Any, None, None]:
    """Context manager DuckDB per leggere parquet su GCS pubblico o locale.

    - Se il path inizia con ``s3://``:
      ``safe_connect(extensions=["httpfs"], config=GCS_S3_CONFIG)``
    - Altrimenti: ``safe_connect()`` (niente httpfs, nessuna estensione)

    Args:
        path: Path al parquet (``s3://dataciviclab-clean/...`` o locale).
        database: Database DuckDB (default ``:memory:``).

    Yields:
        duckdb.DuckDBPyConnection — connessione aperta.

    """
    if _is_s3_path(path):
        with safe_connect(database=database, extensions=["httpfs"], config=GCS_S3_CONFIG) as con:
            yield con
    else:
        with safe_connect(database=database) as con:
            yield con
