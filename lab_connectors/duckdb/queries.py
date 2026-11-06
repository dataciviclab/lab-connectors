"""High-level query helpers per dashboard e analytics.

Fornisce funzioni per caricare clean/mart come ``pandas.DataFrame``,
usando il path contract canonico di ``lab_connectors.gcs.paths``.

Supporta risoluzione GCS (default) e locale (parametro ``local_root``).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    import pandas as pd

# Sorgente dei parquet: auto (locale se disponibile, altrimenti GCS),
# solo locale (errore se manca) o solo GCS.
SourceMode = Literal["auto", "local", "gcs"]


# -- Internal helpers --------------------------------------------------------

# Cache per auto-detection locale (evita FS check ad ogni chiamata)
_UNSET: str = "__auto_detect__"  # sentinel stringa (type-safe per mypy)
_LOCAL_ROOT: str | None = _UNSET


def _detect_local_root(repo_root: Path | None = None) -> str | None:
    """Auto-rileva ``out/data/`` per la risoluzione locale dei parquet.

    .. deprecated::
        Usa :func:`detect_local_root` (pubblico) invece di questa funzione interna.

    Args:
        repo_root: Root del repo da cui cercare. Se fornito, cerca solo lì
            (più veloce e preciso). Se None, fa walking dal CWD (backward compat).

    """
    return detect_local_root(repo_root=repo_root)


def detect_local_root(repo_root: Path | None = None) -> str | None:
    """Auto-rileva ``out/data/`` per la risoluzione locale dei parquet.

    Args:
        repo_root: Root del repo da cui cercare. Se fornito, cerca solo lì
            (più veloce e preciso). Se None, fa walking dal CWD.

    Returns:
        Path assoluto della directory ``out/data/`` se trovata con parquet,
        altrimenti ``None``.

    """
    global _LOCAL_ROOT

    # Fast path: repo_root esplicito
    if repo_root is not None:
        data_dir = repo_root / "out" / "data"
        if data_dir.is_dir() and any(data_dir.rglob("*.parquet")):
            return str(data_dir)
        return None

    if _LOCAL_ROOT is not _UNSET:
        return _LOCAL_ROOT

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
    registry: Any | None = None,
    slug: str = "",
    source: SourceMode = "auto",
    **kwargs: Any,
) -> str:
    """Risolvi URL parquet: GCS o locale.

    Args:
        bucket_key: Chiave bucket (``clean``, ``mart``).
        pattern_key: Chiave del pattern in ``paths.json``.
        prefix: Prefisso GCS del repo (ignorato in locale).
        local_root: Directory ``out/data``. Se ``None`` e ``source`` è
            ``auto``/``local``, viene auto-rilevata.
        registry: Se ``prefix`` è vuoto, il prefix viene letto dal
            ``location.path`` del dataset.
        slug: Slug del dataset.
        source: ``auto`` (default, comportamento storico: locale se
            ``out/data/`` esiste, altrimenti GCS), ``local`` (solo locale,
            errore se non c'è nulla), ``gcs`` (solo GCS).
        **kwargs: Parametri del pattern (``year``, ``table``, ...).

    """
    if source not in ("auto", "local", "gcs"):
        raise ValueError(f"source non supportato: {source!r} (auto|local|gcs)")

    if not prefix and registry is not None and slug:
        from lab_connectors.registry.models import Registry

        if isinstance(registry, Registry) or hasattr(registry, "prefix_for_slug"):
            prefix = registry.prefix_for_slug(slug)

    if source == "gcs":
        from lab_connectors.gcs.paths import https_url

        return https_url(bucket_key, pattern_key, prefix=prefix, slug=slug, **kwargs)

    if local_root is None:
        local_root = _detect_local_root()

    if local_root is None:
        if source == "local":
            raise FileNotFoundError(
                "source='local' ma nessuna directory out/data con parquet è stata trovata"
            )
        from lab_connectors.gcs.paths import https_url

        return https_url(bucket_key, pattern_key, prefix=prefix, slug=slug, **kwargs)

    from lab_connectors.gcs.paths import resolve

    # Local filesystem has no project prefix — only GCS buckets use it.
    rel = resolve(pattern_key, slug=slug, **kwargs)
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


# Errori DuckDB quando un file locale manca: out/data/ esiste ma è parziale
# (tipico in sviluppo: alcuni dataset sono stati costruiti, altri no).
_LOCAL_MISSING_MARKERS = (
    "No files found that match the pattern",
    "No such file or directory",
)


def is_missing_local_file_error(exc: Exception) -> bool:
    """Ritorna ``True`` se l'errore è un file locale assente (``out/data`` parziale)."""
    text = str(exc)
    return any(marker in text for marker in _LOCAL_MISSING_MARKERS)


def _run_with_remote_fallback(
    execute: Callable[[list[str]], Any],
    urls: list[str],
    remote_urls: list[str] | None,
) -> Any:
    """Esegue ``execute(urls)``; su file locale mancante riprova su GCS."""
    try:
        return execute(urls)
    except Exception as exc:
        if remote_urls is None or not is_missing_local_file_error(exc):
            raise
        return execute(remote_urls)


# -- Mart helpers ------------------------------------------------------------


def load_mart_table(
    slug: str,
    table: str,
    year: int | str,
    *,
    prefix: str = "",
    local_root: str | None = None,
    registry: Any | None = None,
    source: SourceMode = "auto",
    fallback_remote: bool = False,
) -> pd.DataFrame:
    """Carica un singolo mart table come DataFrame.

    Usa il path contract: ``{prefix}{slug}/{year}/{table}.parquet`` nel bucket MART.

    Args:
        slug: Slug del dataset.
        table: Nome della tabella mart.
        year: Anno della partizione.
        prefix: Prefisso GCS del repo.
        local_root: Directory ``out/data`` (default: auto-detect).
        registry: Se ``prefix`` è vuoto, deriva il prefix da ``location.path``.
        source: ``auto`` (default), ``local`` o ``gcs``.
        fallback_remote: Se il file locale manca (``out/data`` parziale),
            riprova una volta su GCS.

    """

    def _urls(mode: SourceMode, root: str | None) -> list[str]:
        return [
            _resolve_url(
                "mart",
                "mart_parquet",
                prefix=prefix,
                local_root=root,
                registry=registry,
                slug=slug,
                source=mode,
                year=str(year),
                table=table,
            )
        ]

    urls = _urls(source, local_root)
    remote = _urls("gcs", None) if fallback_remote and source != "gcs" else None
    return _run_with_remote_fallback(
        lambda u: _query_df(f"SELECT * FROM read_parquet('{u[0]}')"), urls, remote
    )


def load_mart_all_years(
    slug: str,
    table: str,
    years: list[int],
    *,
    prefix: str = "",
    local_root: str | None = None,
    union_by_name: bool = True,
    registry: Any | None = None,
    source: SourceMode = "auto",
    fallback_remote: bool = False,
) -> pd.DataFrame:
    """Carica un mart table per tutti gli anni con UNIONByName."""

    def _urls(mode: SourceMode, root: str | None) -> list[str]:
        return [
            _resolve_url(
                "mart",
                "mart_parquet",
                prefix=prefix,
                local_root=root,
                registry=registry,
                slug=slug,
                source=mode,
                year=str(y),
                table=table,
            )
            for y in years
        ]

    urls = _urls(source, local_root)
    remote = _urls("gcs", None) if fallback_remote and source != "gcs" else None
    return _run_with_remote_fallback(
        lambda u: _read_parquet_urls(u, union_by_name=union_by_name), urls, remote
    )


# -- Clean helpers -----------------------------------------------------------


def load_clean(
    slug: str,
    years: list[int],
    *,
    prefix: str = "",
    local_root: str | None = None,
    union_by_name: bool = True,
    registry: Any | None = None,
    source: SourceMode = "auto",
    fallback_remote: bool = False,
) -> pd.DataFrame:
    """Carica il clean layer per uno slug, tutti gli anni richiesti."""

    def _urls(mode: SourceMode, root: str | None) -> list[str]:
        return [
            _resolve_url(
                "clean",
                "clean_parquet",
                prefix=prefix,
                local_root=root,
                registry=registry,
                slug=slug,
                source=mode,
                year=y,
            )
            for y in years
        ]

    urls = _urls(source, local_root)
    remote = _urls("gcs", None) if fallback_remote and source != "gcs" else None
    return _run_with_remote_fallback(
        lambda u: _read_parquet_urls(u, union_by_name=union_by_name), urls, remote
    )


def query_clean(
    slug: str,
    sql: str,
    years: list[int],
    *,
    prefix: str = "",
    local_root: str | None = None,
    table_alias: str = "clean_input",
    registry: Any | None = None,
    source: SourceMode = "auto",
    fallback_remote: bool = False,
) -> pd.DataFrame:
    """Esegue SQL con CTE virtuale sul clean layer.

    Risolve i path per tutti gli anni e crea una CTE ``{table_alias}``
    referenziabile nella query SQL.

    Args:
        slug: Slug del dataset.
        sql: Query SQL che referenzia la CTE ``table_alias``.
        years: Anni da unire nella CTE.
        prefix: Prefisso GCS del repo.
        local_root: Directory ``out/data`` (default: auto-detect).
        table_alias: Nome della CTE virtuale (default ``clean_input``).
        registry: Se ``prefix`` è vuoto, deriva il prefix da ``location.path``.
        source: ``auto`` (default), ``local`` o ``gcs``.
        fallback_remote: Se il file locale manca (``out/data`` parziale),
            riprova una volta su GCS.

    """

    def _urls(mode: SourceMode, root: str | None) -> list[str]:
        return [
            _resolve_url(
                "clean",
                "clean_parquet",
                prefix=prefix,
                local_root=root,
                registry=registry,
                slug=slug,
                source=mode,
                year=y,
            )
            for y in years
        ]

    def _execute(u: list[str]) -> pd.DataFrame:
        paths = "', '".join(u)
        cte = f"WITH {table_alias} AS (SELECT * FROM read_parquet(['{paths}'], union_by_name=true))"
        return _query_df(f"{cte} {sql}")

    urls = _urls(source, local_root)
    remote = _urls("gcs", None) if fallback_remote and source != "gcs" else None
    return _run_with_remote_fallback(_execute, urls, remote)


# -- Utility -----------------------------------------------------------------


def count_rows(
    slug: str,
    year: int | str,
    layer: str = "clean",
    *,
    prefix: str = "",
    local_root: str | None = None,
    registry: Any | None = None,
    source: SourceMode = "auto",
    fallback_remote: bool = False,
) -> int:
    """Conta le righe di un parquet (per verifica)."""

    def _urls(mode: SourceMode, root: str | None) -> list[str]:
        return [
            _resolve_url(
                "clean",
                "clean_parquet",
                prefix=prefix,
                local_root=root,
                registry=registry,
                slug=slug,
                source=mode,
                year=str(year),
            )
        ]

    if layer != "clean":
        raise ValueError(f"Layer {layer!r} non supportato. Usa 'clean'.")

    urls = _urls(source, local_root)
    remote = _urls("gcs", None) if fallback_remote and source != "gcs" else None
    row = _run_with_remote_fallback(
        lambda u: _query_one(f"SELECT COUNT(*) AS n FROM read_parquet('{u[0]}')"),
        urls,
        remote,
    )
    return int(row[0])


__all__ = [
    "SourceMode",
    "count_rows",
    "detect_local_root",
    "is_missing_local_file_error",
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
    local_root: str | None = None,
    registry: Any | None = None,
    source: SourceMode = "auto",
    fallback_remote: bool = False,
) -> pd.DataFrame:
    """Carica un mart table flat (non partizionato per anno).

    Usa il path contract: ``{prefix}{slug}/{table}.parquet`` nel bucket MART.
    Vedi ``load_mart_table`` per ``source``/``fallback_remote``.
    """

    def _urls(mode: SourceMode, root: str | None) -> list[str]:
        return [
            _resolve_url(
                "mart",
                "mart_parquet_flat",
                prefix=prefix,
                local_root=root,
                registry=registry,
                slug=slug,
                source=mode,
                table=table,
            )
        ]

    urls = _urls(source, local_root)
    remote = _urls("gcs", None) if fallback_remote and source != "gcs" else None
    return _run_with_remote_fallback(
        lambda u: _query_df(f"SELECT * FROM read_parquet('{u[0]}')"), urls, remote
    )


# -- Registry helpers -----------------------------------------------------


def years_from_registry(registry: Any, *, slug: str | None = None) -> list[int]:
    """Estrae la lista unica degli anni disponibili da un Registry.

    Se ``slug`` è fornito, restituisce gli anni solo per quel dataset.
    Altrimenti restituisce gli anni unici di tutti i dataset.
    """
    years: set[int] = set()
    for ds in registry.datasets:
        ds_slug = getattr(ds, "slug", None)
        if slug is not None and ds_slug != slug:
            continue
        period = getattr(ds, "period", {})
        start = period.get("start") if isinstance(period, dict) else getattr(period, "start", None)
        end = period.get("end") if isinstance(period, dict) else getattr(period, "end", None)
        if start is not None:
            years.add(int(start))
        if end is not None:
            years.add(int(end))
    return sorted(years)
