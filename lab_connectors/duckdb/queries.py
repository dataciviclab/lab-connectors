"""High-level query helpers per dashboard e analytics su GCS.

Fornisce funzioni per caricare clean/mart da GCS come ``pandas.DataFrame``,
usando il path contract canonico di ``lab_connectors.gcs.paths``.

Usage::

    from lab_connectors.duckdb.queries import (
        load_mart_table, load_mart_all_years,
        load_clean, query_clean, count_rows,
    )

    df = load_mart_table("rna_aiuti_stato", "mart_aiuti_per_regione", 2023)
    df = query_clean("rna_aiuti_stato", "SELECT * FROM clean_input WHERE anno = 2023")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd


# -- Internal helpers --------------------------------------------------------


def _https_url(bucket_key: str, pattern_key: str, *, prefix: str = "", **kwargs: Any) -> str:
    """Lazy import di ``https_url`` per evitare circular import."""
    from lab_connectors.gcs.paths import https_url

    return https_url(bucket_key, pattern_key, prefix=prefix, **kwargs)


def _query_df(sql: str) -> pd.DataFrame:
    """Esegui SQL e restituisci DataFrame. Connessione temporanea."""
    from lab_connectors.duckdb.core import safe_connect

    with safe_connect() as con:
        return con.sql(sql).df()


def _query_one(sql: str) -> tuple[Any, ...]:
    """Esegui SQL e restituisci la prima riga come tupla."""
    from lab_connectors.duckdb.core import safe_connect

    with safe_connect() as con:
        row = con.sql(sql).fetchone()
        if row is None:
            raise RuntimeError("Query restituita vuota")
        return row


def _read_parquet_urls(
    urls: list[str],
    *,
    union_by_name: bool = True,
) -> pd.DataFrame:
    """Leggi multipli parquet da URL e uniscili."""
    if len(urls) == 0:
        raise ValueError("Nessun URL fornito")
    if len(urls) == 1:
        return _query_df(f"SELECT * FROM read_parquet('{urls[0]}')")
    paths = "', '".join(urls)
    union = ", union_by_name=true" if union_by_name else ""
    return _query_df(f"SELECT * FROM read_parquet(['{paths}']{union})")


# -- Mart helpers ------------------------------------------------------------


def load_mart_table(
    slug: str,
    table: str,
    year: int | str,
    *,
    prefix: str = "",
) -> pd.DataFrame:
    """Carica un singolo mart table da GCS come DataFrame.

    Usa il path contract: ``{prefix}{slug}/{year}/{table}.parquet`` nel bucket MART.
    """
    url = _https_url("mart", "mart_parquet", prefix=prefix, slug=slug, year=str(year), table=table)
    return _query_df(f"SELECT * FROM read_parquet('{url}')")


def load_mart_all_years(
    slug: str,
    table: str,
    years: list[int],
    *,
    prefix: str = "",
    union_by_name: bool = True,
) -> pd.DataFrame:
    """Carica un mart table per tutti gli anni con UNIONByName."""
    urls = [
        _https_url("mart", "mart_parquet", prefix=prefix, slug=slug, year=str(y), table=table)
        for y in years
    ]
    return _read_parquet_urls(urls, union_by_name=union_by_name)


# -- Clean helpers -----------------------------------------------------------


def load_clean(
    slug: str,
    years: list[int],
    *,
    prefix: str = "",
    union_by_name: bool = True,
) -> pd.DataFrame:
    """Carica il clean layer per uno slug, tutti gli anni richiesti."""
    urls = [_https_url("clean", "clean_parquet", prefix=prefix, slug=slug, year=y) for y in years]
    return _read_parquet_urls(urls, union_by_name=union_by_name)


def query_clean(
    slug: str,
    sql: str,
    years: list[int],
    *,
    prefix: str = "",
    table_alias: str = "clean_input",
) -> pd.DataFrame:
    """Esegue SQL con CTE virtuale sul clean layer.

    Risolue i path GCS per tutti gli anni e crea una CTE ``{table_alias}``
    referenziabile nella query SQL.
    """
    urls = [_https_url("clean", "clean_parquet", prefix=prefix, slug=slug, year=y) for y in years]
    paths = "', '".join(urls)
    cte = f"WITH {table_alias} AS (SELECT * FROM read_parquet(['{paths}'], union_by_name=true))"
    return _query_df(f"{cte} {sql}")


# -- Utility -----------------------------------------------------------------


def count_rows(
    slug: str,
    year: int | str,
    layer: str = "clean",
    *,
    prefix: str = "",
) -> int:
    """Conta le righe di un parquet su GCS (per verifica)."""
    if layer != "clean":
        raise ValueError(f"Layer {layer!r} non supportato. Usa 'clean'.")
    url = _https_url("clean", "clean_parquet", prefix=prefix, slug=slug, year=str(year))
    row = _query_one(f"SELECT COUNT(*) AS n FROM read_parquet('{url}')")
    return int(row[0])


__all__ = [
    "count_rows",
    "load_clean",
    "load_mart_all_years",
    "load_mart_flat",
    "load_mart_table",
    "query_clean",
    "years_from_registry",
]


# -- Mart flat (non-partitioned) -----------------------------------------


def load_mart_flat(
    slug: str,
    table: str,
    *,
    prefix: str = "",
) -> pd.DataFrame:
    """Carica un mart table flat (non partizionato per anno) da GCS.

    Usa il path contract: ``{prefix}{slug}/{table}.parquet`` nel bucket MART.
    """
    url = _https_url("mart", "mart_parquet_flat", prefix=prefix, slug=slug, table=table)
    return _query_df(f"SELECT * FROM read_parquet('{url}')")


# -- Registry helpers -----------------------------------------------------


def years_from_registry(registry: Any) -> list[int]:
    """Estrae la lista unica degli anni disponibili da un Registry.

    Itera su tutti i dataset e raccoglie ``period.start`` .. ``period.end``.
    """
    years: set[int] = set()
    for ds in registry.datasets:
        period = ds.period if hasattr(ds, "period") else ds.get("period", {})  # type: ignore[union-attr]
        start = period.get("start") if isinstance(period, dict) else getattr(period, "start", None)
        end = period.get("end") if isinstance(period, dict) else getattr(period, "end", None)
        if start is not None:
            years.add(int(start))
        if end is not None:
            years.add(int(end))
    return sorted(years)
