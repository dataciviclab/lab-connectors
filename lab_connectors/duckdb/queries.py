"""High-level query helpers per dashboard e analytics.

Fornisce funzioni per caricare clean/mart come ``pandas.DataFrame``,
usando il path contract canonico di ``lab_connectors.gcs.paths``.

Supporta risoluzione GCS (default) e locale (parametro ``local_root``).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd


# -- Internal helpers --------------------------------------------------------

# Cache per auto-detection locale (evita FS check ad ogni chiamata)
_UNSET: str = "__auto_detect__"  # sentinel stringa (type-safe per mypy)
_LOCAL_ROOT: str | None = _UNSET


def _detect_local_root(repo_root: Path | None = None) -> str | None:
    """Auto-rileva ``out/data/`` per la risoluzione locale dei parquet.

    Args:
        repo_root: Root del repo da cui cercare. Se fornito, cerca solo lì
            (più veloce e preciso). Se None, fa walking dal CWD (backward compat).

    Returns:
        Path ``out/data/`` se trovato, altrimenti None (usa GCS).

    """
    global _LOCAL_ROOT
    if _LOCAL_ROOT is not _UNSET:
        return _LOCAL_ROOT

    # Fast path: repo_root esplicito
    if repo_root is not None:
        data_dir = repo_root / "out" / "data"
        if data_dir.is_dir() and any(data_dir.rglob("*.parquet")):
            _LOCAL_ROOT = str(data_dir)
            return _LOCAL_ROOT
        _LOCAL_ROOT = None
        return None

    # Fallback: walking dal CWD (backward compat)
    cwd = Path.cwd()
    for depth in range(4):  # cwd, ../, ../../, ../../../
        candidate = cwd
        for _ in range(depth):
            candidate = candidate.parent
        data_dir = candidate / "out" / "data"
        if data_dir.is_dir() and any(data_dir.rglob("*.parquet")):
            _LOCAL_ROOT = str(data_dir)
            return _LOCAL_ROOT

    _LOCAL_ROOT = None
    return None


def _resolve_url(
    bucket_key: str,
    pattern_key: str,
    *,
    prefix: str = "",
    local_root: str | None = None,
    repo_root: Path | None = None,
    **kwargs: Any,
) -> str:
    """Risolvi URL parquet: GCS (default) o locale.

    Se ``local_root`` è fornito esplicitamente, lo usa.
    Altrimenti auto-rileva ``out/data/`` dal cwd o dal repo_root.

    Args:
        bucket_key: Chiave bucket (``clean``, ``mart``).
        pattern_key: Chiave del pattern.
        prefix: Prefisso opzionale (es. ``"open-politica/"``).
        local_root: Path locale ``out/data/``. Se None, auto-detect.
        repo_root: Root del repo per auto-detection locale. Se None, usa CWD.
        **kwargs: Parametri del pattern (``slug``, ``year``, ``table``).

    """
    if local_root is None:
        local_root = _detect_local_root(repo_root)

    if local_root is None:
        from lab_connectors.gcs.paths import https_url

        return https_url(bucket_key, pattern_key, prefix=prefix, **kwargs)

    from lab_connectors.gcs.paths import resolve

    # Local filesystem has no project prefix — only GCS buckets use it.
    rel = resolve(pattern_key, **kwargs)
    return f"{local_root}/{bucket_key}/{rel}"


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
    local_root: str | None = None,
) -> pd.DataFrame:
    """Carica un singolo mart table come DataFrame.

    Usa il path contract: ``{prefix}{slug}/{year}/{table}.parquet`` nel bucket MART.
    Se ``local_root`` è fornito, risolve localmente invece che su GCS.
    """
    url = _resolve_url(
        "mart",
        "mart_parquet",
        prefix=prefix,
        local_root=local_root,
        slug=slug,
        year=str(year),
        table=table,
    )
    return _query_df(f"SELECT * FROM read_parquet('{url}')")


def load_mart_all_years(
    slug: str,
    table: str,
    years: list[int],
    *,
    prefix: str = "",
    local_root: str | None = None,
    union_by_name: bool = True,
) -> pd.DataFrame:
    """Carica un mart table per tutti gli anni con UNIONByName."""
    urls = [
        _resolve_url(
            "mart",
            "mart_parquet",
            prefix=prefix,
            local_root=local_root,
            slug=slug,
            year=str(y),
            table=table,
        )
        for y in years
    ]
    return _read_parquet_urls(urls, union_by_name=union_by_name)


# -- Clean helpers -----------------------------------------------------------


def load_clean(
    slug: str,
    years: list[int],
    *,
    prefix: str = "",
    local_root: str | None = None,
    union_by_name: bool = True,
) -> pd.DataFrame:
    """Carica il clean layer per uno slug, tutti gli anni richiesti."""
    urls = [
        _resolve_url(
            "clean", "clean_parquet", prefix=prefix, local_root=local_root, slug=slug, year=y
        )
        for y in years
    ]
    return _read_parquet_urls(urls, union_by_name=union_by_name)


def query_clean(
    slug: str,
    sql: str,
    years: list[int],
    *,
    prefix: str = "",
    local_root: str | None = None,
    table_alias: str = "clean_input",
) -> pd.DataFrame:
    """Esegue SQL con CTE virtuale sul clean layer.

    Risolue i path per tutti gli anni e crea una CTE ``{table_alias}``
    referenziabile nella query SQL. Se ``local_root`` è fornito, risolve
    localmente invece che su GCS.
    """
    urls = [
        _resolve_url(
            "clean", "clean_parquet", prefix=prefix, local_root=local_root, slug=slug, year=y
        )
        for y in years
    ]
    paths = "', '".join(urls)
    cte = f"WITH {table_alias} AS (SELECT * FROM read_parquet(['{paths}'], union_by_name=true))"
    return _query_df(f"{cte} {sql}")


# -- Utility -----------------------------------------------------------------


def detect_local_root() -> str | None:
    """Rileva ``out/data/`` locale (public API).

    Wrapper pubblico per ``_detect_local_root()``.
    Se trovato, i path vengono risolti localmente invece che su GCS.

    Returns:
        Path ``out/data/`` se trovato, altrimenti None (usa GCS).

    """
    return _detect_local_root()


def years_for_slug(registry: Any, slug: str) -> list[int]:
    """Estrae la lista degli anni disponibili per uno slug specifico.

    Args:
        registry: Oggetto Registry.
        slug: Slug del dataset.

    Returns:
        Lista ordinata di anni (es. ``[2020, 2021, 2022]``).

    """
    ds = next((d for d in registry.datasets if d.slug == slug), None)
    if ds is None:
        return []

    period = ds.period if hasattr(ds, "period") else {}
    if not isinstance(period, dict):
        period = {"start": getattr(period, "start", None), "end": getattr(period, "end", None)}

    start = period.get("start")
    end = period.get("end")
    if start is not None and end is not None:
        return list(range(int(start), int(end) + 1))
    return []


def count_rows(
    slug: str,
    year: int | str,
    layer: str = "clean",
    *,
    prefix: str = "",
    local_root: str | None = None,
) -> int:
    """Conta le righe di un parquet (per verifica)."""
    if layer != "clean":
        raise ValueError(f"Layer {layer!r} non supportato. Usa 'clean'.")
    url = _resolve_url(
        "clean", "clean_parquet", prefix=prefix, local_root=local_root, slug=slug, year=str(year)
    )
    row = _query_one(f"SELECT COUNT(*) AS n FROM read_parquet('{url}')")
    return int(row[0])


__all__ = [
    "count_rows",
    "detect_local_root",
    "load_clean",
    "load_mart_all_years",
    "load_mart_flat",
    "load_mart_table",
    "query_clean",
    "years_for_slug",
    "years_from_registry",
]


# -- Mart flat (non-partitioned) -----------------------------------------


def load_mart_flat(
    slug: str,
    table: str,
    *,
    prefix: str = "",
    local_root: str | None = None,
) -> pd.DataFrame:
    """Carica un mart table flat (non partizionato per anno).

    Usa il path contract: ``{prefix}{slug}/{table}.parquet`` nel bucket MART.
    Se ``local_root`` è fornito, risolve localmente invece che su GCS.
    """
    url = _resolve_url(
        "mart", "mart_parquet_flat", prefix=prefix, local_root=local_root, slug=slug, table=table
    )
    return _query_df(f"SELECT * FROM read_parquet('{url}')")


# -- Registry helpers -----------------------------------------------------


def years_from_registry(registry: Any) -> list[int]:
    """Estrae la lista unica degli anni disponibili da un Registry.

    Itera su tutti i dataset e raccoglie ``period.start`` .. ``period.end``.
    I dataset con ``location.multi_file=False`` (cumulativi, single-file)
    vengono esclusi: non hanno parquet per-anno.
    """
    years: set[int] = set()
    for ds in registry.datasets:
        # Salta dataset single-file (cumulativi, es. rna_misure)
        loc = getattr(ds, "location", None)
        if loc is not None:
            mf = getattr(loc, "multi_file", True)
            if not mf:
                continue
        period = ds.period if hasattr(ds, "period") else ds.get("period", {})
        start = period.get("start") if isinstance(period, dict) else getattr(period, "start", None)
        end = period.get("end") if isinstance(period, dict) else getattr(period, "end", None)
        if start is not None:
            years.add(int(start))
        if end is not None:
            years.add(int(end))
    return sorted(years)
