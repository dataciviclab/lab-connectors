"""Path contract GCS per DataCivicLab.

Carica ``paths.json`` e fornisce risoluzione pattern e composizione URL.
Pattern e bucket names sono nel JSON; questo modulo è solo un wrapper tipato.

Usage::

    from lab_connectors.gcs.paths import gs_url, resolve

    resolve("clean_parquet", slug="demo", year=2024)
    # → "demo/2024/demo_2024_clean.parquet"

    gs_url("clean", "clean_parquet", slug="demo", year=2024)
    # → "gs://dataciviclab-clean/demo/2024/demo_2024_clean.parquet"
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Caricamento contratto (lazy, thread-safe)
# ---------------------------------------------------------------------------

_CONTRACT_PATH = Path(__file__).resolve().parent / "paths.json"
_CONTRACT: dict[str, Any] | None = None
_CONTRACT_LOCK = threading.Lock()


def load_contract() -> dict[str, Any]:
    """Carica paths.json. Lazy, thread-safe. Fallisce forte se manca."""
    global _CONTRACT
    if _CONTRACT is not None:
        return _CONTRACT
    with _CONTRACT_LOCK:
        if _CONTRACT is not None:
            return _CONTRACT
        try:
            _CONTRACT = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise RuntimeError(
                f"paths.json non trovato in {_CONTRACT_PATH}. "
                "Include il file in pyproject.toml [tool.setuptools.package-data]."
            ) from None
        return _CONTRACT


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_bucket(bucket_key: str) -> str:
    """Nome bucket per chiave (``clean``, ``mart``)."""
    buckets = load_contract()["buckets"]
    if bucket_key not in buckets:
        raise KeyError(f"Bucket sconosciuto: {bucket_key!r}. Options: {list(buckets)}")
    return buckets[bucket_key]


def resolve(pattern_key: str, **kwargs: Any) -> str:
    """Risolve un pattern in path relativo al bucket root.

    I pattern senza placeholder (es. ``catalog_manifest``) non richiedono kwargs.
    Quelli con placeholder (es. ``clean_parquet``) richiedono ``slug``, ``year`` ecc.
    """
    patterns = load_contract()["patterns"]
    if pattern_key not in patterns:
        raise KeyError(f"Pattern sconosciuto: {pattern_key!r}. Options: {list(patterns)}")
    try:
        return patterns[pattern_key].format(**kwargs)
    except KeyError as e:
        raise KeyError(
            f"Parametro mancante per {pattern_key!r}: {e}. "
            f"Template: {patterns[pattern_key]!r}"
        ) from None


def gs_url(bucket_key: str, pattern_key: str, **kwargs: Any) -> str:
    """URL ``gs://<bucket>/<path>``."""
    return f"gs://{get_bucket(bucket_key)}/{resolve(pattern_key, **kwargs)}"


def https_url(bucket_key: str, pattern_key: str, **kwargs: Any) -> str:
    """URL pubblico ``https://storage.googleapis.com/<bucket>/<path>``."""
    bucket = get_bucket(bucket_key)
    return f"https://storage.googleapis.com/{bucket}/{resolve(pattern_key, **kwargs)}"


# ---------------------------------------------------------------------------
# GCS URL parsing
# ---------------------------------------------------------------------------


def parse_gs_url(url: str) -> tuple[str, str]:
    """Analizza un URL ``gs://`` in (bucket, key).

    Args:
        url: URL del tipo ``gs://dataciviclab-clean/demo/2024/file.parquet``.

    Returns:
        Tupla ``(bucket, key)`` — es. ``("dataciviclab-clean", "demo/2024/file.parquet")``.

    Raises:
        ValueError: se l'URL non inizia con ``gs://``.


    Example::

        >>> parse_gs_url("gs://bucket/path/to/file.parquet")
        ("bucket", "path/to/file.parquet")

    """
    if not url.startswith("gs://"):
        raise ValueError(f"URL deve iniziare con gs://, ricevuto: {url}")
    rest = url[5:]  # rimuovi 'gs://'
    bucket, sep, key = rest.partition("/")
    if not sep:
        raise ValueError(f"URL gs:// senza path: {url}")
    return (bucket, key)


# ---------------------------------------------------------------------------
# Bucket names (costanti — corrispondono a paths.json)
# ---------------------------------------------------------------------------

CLEAN_BUCKET: str = get_bucket("clean")
MART_BUCKET: str = get_bucket("mart")

# ---------------------------------------------------------------------------
# Glob pattern → regex
# ---------------------------------------------------------------------------


def glob_to_regex(pattern: str) -> str:
    r"""Convert a glob pattern to regex.

    Supporta ``*`` (qualsiasi sequenza), ``**`` (qualsiasi profondità),
    e ``?`` (un carattere).

    Args:
        pattern: Pattern glob (es. ``"candidates/*/dataset.yml"``).

    Returns:
        Stringa regex (es. ``"candidates/[^/]*/dataset\.yml"``).

    Example::

        >>> import re
        >>> rx = glob_to_regex("*.parquet")
        >>> re.match(rx, "data.parquet") is not None
        True

    """
    parts: list[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        c = pattern[i]
        if c == "*" and i + 1 < n and pattern[i + 1] == "*":
            # ** = qualsiasi profondità
            parts.append(".*")
            i += 2
            # skip eventuale /
            if i < n and pattern[i] == "/":
                i += 1
        elif c == "*":
            parts.append("[^/]*")
            i += 1
        elif c == "?":
            parts.append(".")
            i += 1
        elif c in ".^$+{}[]\\|()":
            parts.append("\\" + c)
            i += 1
        else:
            parts.append(c)
            i += 1
    return "".join(parts)


# ---------------------------------------------------------------------------
# Convenience functions usate dai consumer
# ---------------------------------------------------------------------------


def pipeline_run(slug: str, year: int | str) -> str:
    """Path ``{slug}/{year}/pipeline_run.json``."""
    return resolve("pipeline_run", slug=slug, year=str(year))


def catalog_manifest() -> str:
    """Path ``catalog/manifest.json``."""
    return resolve("catalog_manifest")


def mart_parquet(slug: str, year: int | str, table: str) -> str:
    """Path ``{slug}/{year}/{table}.parquet`` nel bucket MART.

    Args:
        slug: Dataset slug (es. ``ispra_ru_base``).
        year: Anno (int o stringa).
        table: Nome della tabella MART (es. ``costi_procapite``).

    Returns:
        Path relativo al bucket root, es. ``ispra_ru_base/2024/costi.parquet``.

    """
    return resolve("mart_parquet", slug=slug, year=str(year), table=table)


__all__ = [
    "load_contract",
    "get_bucket",
    "resolve",
    "gs_url",
    "https_url",
    "parse_gs_url",
    "glob_to_regex",
    "CLEAN_BUCKET",
    "MART_BUCKET",
    "pipeline_run",
    "catalog_manifest",
    "mart_parquet",
]
