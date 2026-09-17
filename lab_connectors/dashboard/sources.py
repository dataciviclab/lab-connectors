"""Data source helpers per dashboard Streamlit.

Fornisce funzioni per caricare e cachare dati dai layer clean/mart,
riducendo il boilerplate in ogni ``sources.py`` di dashboard.

Usage::

    from lab_connectors.dashboard.sources import init_sources, make_cached_sources

    # Init: carica registry, estrai anni
    registry, YEARS = init_sources(
        repo_root=Path(__file__).parent.parent,
        prefix="mio-repo/",
    )

    # Wrapper cachati per load_mart, query, count_rows
    sources = make_cached_sources(
        prefix="mio-repo/",
        slugs=["mio_slug"],
    )

    # Nelle pagine:
    df = sources.load_mart("mart_table", 2026)
    df = sources.query("SELECT * FROM clean_input LIMIT 10")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def init_sources(
    repo_root: Path,
    prefix: str = "",
    slugs: list[str] | None = None,
) -> tuple[Any, list[int], Any]:
    """Inizializzazione condivisa: load_registry + extract YEARS.

    Args:
        repo_root: Root del repo (contiene ``registry/registry.json``).
        prefix: Prefisso GCS per il path contract.
        slugs: Slugs opzionali per filtrare (unused, kept for compat).

    Returns:
        ``(registry, years, registry)`` — il terzo elemento e' per backward
        compat con ``_sources, YEARS, registry = init_sources(...)``.

    """
    from lab_connectors.duckdb.queries import years_from_registry
    from lab_connectors.registry import load_registry

    registry = load_registry(repo_root / "registry" / "registry.json")
    years = years_from_registry(registry)
    return registry, years, registry


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


def detect_local_root(repo_root: Path | None = None) -> str | None:
    """Rileva ``out/data/`` locale (public API).

    Wrapper pubblico per ``_detect_local_root()``.

    Args:
        repo_root: Root del repo da cui cercare. Se None, usa auto-detection.

    Returns:
        Path ``out/data/`` se trovato, altrimenti None (usa GCS).

    """
    from lab_connectors.duckdb.queries import _detect_local_root

    return _detect_local_root(repo_root)


def make_cached_sources(
    prefix: str,
    slugs: list[str],
    default_year: int | None = None,
    ttl: int = 3600,
) -> CachedSources:
    """Genera wrapper cachati Streamlit per load_mart e query.

    Args:
        prefix: Prefisso GCS per il path contract.
        slugs: Slugs dei dataset disponibili.
        default_year: Anno di default (se None, usa il primo anno disponibile).
        ttl: TTL per la cache Streamlit (default: 3600s = 1h).

    Returns:
        Oggetto ``CachedSources`` con metodi cachati.

    """
    return CachedSources(prefix=prefix, slugs=slugs, default_year=default_year, ttl=ttl)


class CachedSources:
    """Wrapper cachati per load_mart, query, count_rows.

    Generato da ``make_cached_sources()``. Ogni metodo e' decorato con
    ``@st.cache_data`` e wrappa le funzioni di ``lab_connectors.duckdb.queries``.
    """

    def __init__(
        self,
        prefix: str,
        slugs: list[str],
        default_year: int | None = None,
        ttl: int = 3600,
    ) -> None:
        """Inizializza CachedSources.

        Args:
            prefix: Prefisso GCS per il path contract.
            slugs: Slugs dei dataset disponibili.
            default_year: Anno di default.
            ttl: TTL per la cache Streamlit.

        """
        self.prefix = prefix
        self.slugs = slugs
        self.default_year = default_year
        self.ttl = ttl

    def load_mart(
        self,
        slug: str,
        table: str,
        year: int | None = None,
    ) -> Any:
        """Carica un singolo mart table (cached)."""
        import streamlit as st

        from lab_connectors.duckdb.queries import load_mart_table

        @st.cache_data(ttl=self.ttl, show_spinner=False)
        def _load_mart_inner(slug: str, table: str, year: int) -> Any:
            return load_mart_table(slug, table, year, prefix=self.prefix)

        y = year if year is not None else (self.default_year or 0)
        return _load_mart_inner(slug, table, y)

    def query(
        self,
        slug: str,
        sql: str,
        years: list[int] | None = None,
    ) -> Any:
        """Esegue SQL sul clean layer (cached)."""
        import streamlit as st

        from lab_connectors.duckdb.queries import query_clean

        @st.cache_data(ttl=self.ttl, show_spinner=False)
        def _query_inner(sql: str, years_key: tuple[int, ...]) -> Any:
            return query_clean(slug, sql, list(years_key), prefix=self.prefix)

        return _query_inner(sql, tuple(years or []))

    def count_rows(
        self,
        slug: str,
        year: int,
    ) -> int:
        """Conta righe clean per un anno (cached)."""
        import streamlit as st

        from lab_connectors.duckdb.queries import count_rows

        @st.cache_data(ttl=self.ttl, show_spinner=False)
        def _count_inner(slug: str, year: int) -> int:
            return count_rows(slug, year, prefix=self.prefix)

        return _count_inner(slug, year)
