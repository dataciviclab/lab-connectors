"""Derivazione delle location GCS dal contratto registry v2.

Nel registry v2 i path non sono più scritti voce per voce: il file dichiara il
contratto di pubblicazione del repo (``gcs.prefix``, ``gcs.clean``) e i mart
dichiarano solo *come* sono partizionati (``layout``). Questo modulo traduce
quel contratto in ``location`` compatibili con lo schema v1, così i consumer
continuano a leggere ``ds.location.path`` senza sapere la versione del file.

Regole (verificate sui 45 registry del workspace: 544/544 clean, 1.197/1.197 mart):

- clean ``year``, 1 partizione → path puntuale ``{slug}/{year}/{slug}_{year}_clean.parquet``
- clean ``year``, >1 partizioni → glob ``{slug}/*/{slug}_*_clean.parquet``
- clean ``flat``, 1 partizione → path puntuale ``{slug}/{slug}_{year}_clean.parquet``
- clean ``flat``, >1 partizioni → glob ``{slug}/{slug}_*_clean.parquet``
- clean senza partizioni (mart-only) → nessuna location
- mart ``flat`` → ``{dataset}/{table}.parquet``
- mart ``year`` → ``{dataset}/{year}/{table}.parquet``
- mart ``glob`` → ``{dataset}/*/{table}.parquet``
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lab_connectors.gcs.paths import get_bucket, gs_url

CLEAN_LAYOUTS = frozenset({"year", "flat"})
MART_LAYOUTS = frozenset({"flat", "year", "glob"})


def normalize_prefix(prefix: str | None) -> str:
    """Prefisso GCS con trailing slash (``""`` resta vuoto)."""
    p = (prefix or "").strip()
    if not p:
        return ""
    return p.rstrip("/") + "/"


def _partition_years(partitions: Mapping[Any, int] | None) -> list[int]:
    """Chiavi di partizione ordinate come interi (anno o legislatura)."""
    if not partitions:
        return []
    years: list[int] = []
    for key in partitions:
        try:
            years.append(int(key))
        except (TypeError, ValueError):
            continue
    return sorted(years)


def clean_location(
    prefix: str,
    layout: str,
    slug: str,
    partitions: Mapping[Any, int] | None,
) -> dict[str, object] | None:
    """``location`` clean derivata dal contratto (None se non c'è clean)."""
    years = _partition_years(partitions)
    if not years:
        return None
    if layout not in CLEAN_LAYOUTS:
        raise ValueError(f"gcs.clean non valido: {layout!r} (year|flat)")
    prefix = normalize_prefix(prefix)
    if len(years) == 1:
        pattern = "clean_parquet_flat" if layout == "flat" else "clean_parquet"
        return {
            "type": "gcs",
            "path": gs_url("clean", pattern, prefix=prefix, slug=slug, year=str(years[-1])),
            "multi_file": False,
        }
    bucket = get_bucket("clean")
    if layout == "flat":
        path = f"gs://{bucket}/{prefix}{slug}/{slug}_*_clean.parquet"
    else:
        path = f"gs://{bucket}/{prefix}{slug}/*/{slug}_*_clean.parquet"
    return {"type": "gcs", "path": path, "multi_file": True}


def mart_location(
    prefix: str,
    dataset: str,
    table: str,
    layout: str,
    year: int | None = None,
) -> dict[str, object]:
    """``location`` mart derivata dal contratto (``layout`` flat|year|glob)."""
    if layout not in MART_LAYOUTS:
        raise ValueError(f"layout mart non valido: {layout!r} (flat|year|glob)")
    prefix = normalize_prefix(prefix)
    if layout == "flat":
        return {
            "type": "gcs",
            "path": gs_url("mart", "mart_parquet_flat", prefix=prefix, slug=dataset, table=table),
            "multi_file": False,
        }
    if layout == "year":
        if year is None:
            raise ValueError(f"layout 'year' richiede l'anno per il mart '{dataset}__{table}'")
        return {
            "type": "gcs",
            "path": gs_url(
                "mart", "mart_parquet", prefix=prefix, slug=dataset, year=str(year), table=table
            ),
            "multi_file": False,
        }
    bucket = get_bucket("mart")
    return {
        "type": "gcs",
        "path": f"gs://{bucket}/{prefix}{dataset}/*/{table}.parquet",
        "multi_file": True,
    }


__all__ = [
    "CLEAN_LAYOUTS",
    "MART_LAYOUTS",
    "clean_location",
    "mart_location",
    "normalize_prefix",
]
