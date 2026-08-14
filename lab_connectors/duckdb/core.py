"""Context manager ``safe_connect`` per connessioni DuckDB.

Elimina il pattern ``duckdb.connect()`` + ``try/finally`` + ``con.close()``
duplicato in 3+ repo del Lab.

Supporta estensioni (es. ``httpfs`` per GCS) e configurazione DuckDB.
``safe_connect`` fa ``INSTALL`` + ``LOAD`` per ogni estensione,
quindi funziona anche su runner CI pulito.

Configurazioni di default applicate automaticamente (override via ``config``):
    - ``memory_limit``: ``'2GB'`` (override via env ``DUCKDB_MEMORY_LIMIT``
      o parametro ``config``) — utile per dataset con join pesanti (es.
      clean su >4M righe) dove il default 2GB causa OOM anche su runner
      con RAM abbondante
    - ``PRAGMA disable_progress_bar``: sempre attivo

Uso::

    from lab_connectors.duckdb import safe_connect

    with safe_connect() as con:
        result = con.execute("SELECT 1").fetchall()

    # HTTPS diretto su GCS (stabile, senza estensioni)
    with gcs_connect("https://storage.googleapis.com/...") as con:
        con.execute("SELECT * FROM read_parquet('https://...')")
"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# ── Configurazione DuckDB per bucket GCS pubblici via S3-compatible API ───────
# Mantenuta per backward compat. Preferire HTTPS che non richiede httpfs
# ed evita il bug DuckDB "Information loss on integer cast".

GCS_S3_CONFIG: dict[str, str] = {
    "s3_endpoint": "storage.googleapis.com",
    "s3_region": "auto",
    "s3_access_key_id": "",
    "s3_secret_access_key": "",
    "s3_use_ssl": "true",
}

# Memory limit DuckDB: override via env DUCKDB_MEMORY_LIMIT (es. "4GB"),
# altrimenti il default 2GB. Il parametro config di safe_connect vince su tutto.
_MEMORY_LIMIT_ENV = "DUCKDB_MEMORY_LIMIT"
_DEFAULT_MEMORY_LIMIT = "2GB"
# Threads e preserve_insertion_order: override via env (es. runner CI con
# poca RAM: DUCKDB_THREADS=2 e DUCKDB_PRESERVE_INSERTION_ORDER=false riducono
# il picco di memoria). Default = comportamento DuckDB standard.
_THREADS_ENV = "DUCKDB_THREADS"
_PRESERVE_ORDER_ENV = "DUCKDB_PRESERVE_INSERTION_ORDER"


def _default_config() -> dict[str, str]:
    limit = os.environ.get(_MEMORY_LIMIT_ENV, _DEFAULT_MEMORY_LIMIT)
    return {"memory_limit": limit}


def _apply_env_settings(con) -> None:
    """Applica i limiti da env (threads, preserve) per runner CI con poca RAM."""
    t = os.environ.get(_THREADS_ENV)
    if t:
        con.execute(f"SET threads={int(t)}")
    po = os.environ.get(_PRESERVE_ORDER_ENV)
    if po and po.lower() in ("false", "0"):
        con.execute("SET preserve_insertion_order=false")


@contextmanager
def safe_connect(
    database: str = ":memory:",
    extensions: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> Generator[Any, None, None]:
    """Context manager per connessioni DuckDB.

    Applica la config di default (``memory_limit`` da ``DUCKDB_MEMORY_LIMIT``
    o ``'2GB'``) e ``PRAGMA disable_progress_bar``.

    Args:
        database: Path al database o ``":memory:"`` (default).
        extensions: Lista di estensioni DuckDB (``["httpfs"]``, ``["icu"]``).
        config: Config DuckDB (es. ``GCS_S3_CONFIG``). Sovrascrive i default,
            incluse le env var.

    Yields:
        duckdb.DuckDBPyConnection — connessione aperta.

    """
    import duckdb

    merged_config: dict[str, Any] = {**_default_config(), **(config or {})}

    con = duckdb.connect(database, config=merged_config)
    try:
        con.execute("PRAGMA disable_progress_bar")
        _apply_env_settings(con)
        if extensions:
            for ext in extensions:
                con.execute(f"INSTALL {ext}")
                con.execute(f"LOAD {ext}")
        # httpfs: la config passata a duckdb.connect() non viene riconosciuta
        # dall'estensione. Va applicata via SET dopo LOAD.
        if config:
            for k, v in config.items():
                if k.startswith("s3_"):
                    con.execute(f"SET {k} = '{v}'")
        yield con
    finally:
        try:
            con.close()
        except Exception:
            pass


@contextmanager
def gcs_connect(
    path: str | Path,
    database: str = ":memory:",
) -> Generator[Any, None, None]:
    """Context manager per leggere parquet da GCS via DuckDB.

    DuckDB legge ``https://storage.googleapis.com/...`` nativamente
    senza estensioni (stabile, senza bug httpfs).

    Per path ``s3://...`` o ``gs://...`` (inclusi glob multi-file
    ``gs://bucket/slug/*/*.parquet``) carica httpfs (backward compat
    e unica via per i glob: HTTP generico non supporta glob).

    Args:
        path: Path al parquet (HTTPS preferito per stabilità).
        database: Database DuckDB (default ``:memory:``).

    Yields:
        duckdb.DuckDBPyConnection — connessione aperta.

    """
    s = str(path)
    # Tolleranza doppio/singolo slash per coerenza con s3:// e s3:/ (gs:/ non
    # è mai stato usato, ma il pattern resta simmetrico e il routing corretto).
    needs_httpfs = s.startswith(("s3://", "s3:/", "gs://", "gs:/"))
    if needs_httpfs:
        with safe_connect(database=database, extensions=["httpfs"], config=GCS_S3_CONFIG) as con:
            yield con
    else:
        with safe_connect(database=database) as con:
            yield con
