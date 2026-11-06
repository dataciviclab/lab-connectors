"""Disponibilità degli anni per i dataset pubblicati.

Due nozioni diverse, spesso confuse nei consumer:

- **anni dichiarati**: l'intervallo ``period.start - period.end`` del registry
  (``year_range``);
- **anni effettivamente pubblicati**: le partizioni presenti su GCS, dedotte da
  ``location.path`` e, per i layout multi-file, verificate con un HEAD
  (``published_years`` / ``latest_published_year``).

Usage::

    from lab_connectors.registry import load_registry
    from lab_connectors.registry.availability import latest_published_year, year_range

    reg = load_registry(Path("repo/registry/registry.json"))
    latest_published_year(reg, "ispra_ru_base")   # 2024
    year_range(reg, slug="ispra_ru_base")         # [2019, ..., 2024]
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lab_connectors.registry.models import Dataset, Registry

_YEAR_SEGMENT = re.compile(r"/(\d{4})/")

# Probe iniettabile: riceve un URI gs:// e dice se l'oggetto esiste.
Probe = Callable[[str], bool]


def _extract_years(period: Any) -> list[int]:
    """Anni dichiarati in un ``period`` (dict o dataclass-like)."""
    if not period:
        return []
    if isinstance(period, dict):
        start = period.get("start")
        end = period.get("end")
    else:
        start = getattr(period, "start", None)
        end = getattr(period, "end", None)
    if start is None or end is None:
        return []
    try:
        first, last = int(start), int(end)
    except (TypeError, ValueError):
        return []
    if last < first:
        return []
    return list(range(first, last + 1))


def _find_dataset(registry: Registry, slug: str) -> Dataset | None:
    return next((ds for ds in registry.datasets if ds.slug == slug), None)


def year_range(
    registry: Registry,
    *,
    slug: str | None = None,
    local_root: str | Path | None = None,
    layer: str = "clean",
) -> list[int]:
    """Anni dichiarati nel registry, con filtro opzionale sui file locali.

    A differenza di ``duckdb.queries.years_from_registry`` (che restituisce solo
    gli estremi) questa funzione restituisce **tutti** gli anni dell'intervallo,
    che è ciò che serve alle dashboard per costruire i selettori.

    Args:
        registry: Registry del repo produttore.
        slug: Se fornito, limita gli anni a quel dataset.
        local_root: Directory ``out/data`` locale. Se fornita, tiene solo gli
            anni con una directory ``{local_root}/{layer}/{slug}/{year}``.
        layer: Layer usato per il filtro locale (default ``clean``).

    Returns:
        Anni in ordine crescente (lista vuota se il period è assente).

    """
    years: set[int] = set()
    for ds in registry.datasets:
        if slug is not None and ds.slug != slug:
            continue
        referred = _extract_years(ds.period)
        if local_root is not None:
            base = Path(local_root) / layer / ds.slug
            referred = [y for y in referred if (base / str(y)).is_dir()]
        years.update(referred)
    return sorted(years)


def _default_probe(gs_uri: str) -> bool:
    """HEAD pubblico su GCS. Import lazy: l'extra ``gcs`` resta opzionale."""
    from lab_connectors.gcs.client import object_exists
    from lab_connectors.gcs.paths import parse_gs_url

    bucket, key = parse_gs_url(gs_uri)
    return object_exists(bucket, key)


def _substitute_year(template: str, year: int) -> str:
    return template.replace("*", str(year))


def published_years(
    registry: Registry,
    slug: str,
    *,
    probe: Probe | None = None,
    today_year: int | None = None,
) -> list[int]:
    """Anni con una partizione presente su GCS per il dataset.

    Con ``location.path`` puntuale (``multi_file: false``) l'anno è ricavato dal
    path senza rete. Con un glob l'anno viene sostituito nel template e
    verificato con ``probe``; i candidati sono quelli del ``period`` del
    registry (se assente si usano gli ultimi 10 anni).

    Args:
        registry: Registry del repo produttore.
        slug: Slug del dataset.
        probe: Funzione ``gs_uri -> bool``. Default: HEAD pubblico su GCS.
        today_year: Anno corrente (iniettabile nei test).

    Returns:
        Anni pubblicati in ordine crescente.

    """
    ds = _find_dataset(registry, slug)
    if ds is None:
        return []

    path = (ds.location.path or "") if ds.location else ""
    if not path.startswith("gs://"):
        return []

    if "*" not in path:
        match = _YEAR_SEGMENT.search(path)
        return [int(match.group(1))] if match else []

    candidates = _extract_years(ds.period)
    if not candidates:
        current = today_year or datetime.now(UTC).year
        candidates = list(range(current - 9, current + 1))

    check = probe or _default_probe
    return [y for y in candidates if check(_substitute_year(path, y))]


def latest_published_year(
    registry: Registry,
    slug: str,
    *,
    prefix: str | None = None,
    layer: str = "clean",
    table: str | None = None,
    probe: Probe | None = None,
    today_year: int | None = None,
) -> int:
    """Anno più recente con dati pubblicati.

    Ordine di risoluzione:

    1. anno/i da ``location.path`` (``published_years``);
    2. probe HEAD sulle partizioni ``{prefix}{slug}/{year}/...`` per l'anno
       corrente e i due precedenti;
    3. anno corrente.

    Args:
        registry: Registry del repo produttore.
        slug: Slug del dataset.
        prefix: Prefisso GCS del repo. Default: ``registry.prefix_for_slug``.
        layer: ``clean`` (default) o ``mart`` (richiede ``table``).
        table: Nome tabella mart (obbligatorio con ``layer="mart"``).
        probe: Funzione ``gs_uri -> bool`` (default: HEAD su GCS).
        today_year: Anno corrente (iniettabile nei test).

    Returns:
        Anno più recente disponibile.

    Raises:
        ValueError: se ``layer="mart"`` senza ``table``.

    """
    if layer not in ("clean", "mart"):
        raise ValueError(f"layer non supportato: {layer!r} (clean|mart)")
    if layer == "mart" and not table:
        raise ValueError('layer="mart" richiede il parametro table')

    found = published_years(registry, slug, probe=probe, today_year=today_year)
    if found:
        return max(found)

    from lab_connectors.gcs.paths import gs_url

    current = today_year or datetime.now(UTC).year
    check = probe or _default_probe
    resolved_prefix = prefix
    if resolved_prefix is None:
        resolved_prefix = registry.prefix_for_slug(slug)

    for year in range(current + 1, current - 3, -1):
        if layer == "mart":
            uri = gs_url(
                "mart",
                "mart_parquet",
                prefix=resolved_prefix,
                slug=slug,
                year=str(year),
                table=table,
            )
        else:
            uri = gs_url(
                "clean",
                "clean_parquet",
                prefix=resolved_prefix,
                slug=slug,
                year=str(year),
            )
        if check(uri):
            return year
    return current


__all__ = ["Probe", "latest_published_year", "published_years", "year_range"]
