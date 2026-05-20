"""Path contract GCS — source of truth per i path degli artifact su GCS.

Questo modulo carica ``paths.json`` (nella stessa directory) e fornisce:

- ``resolve(pattern_key, **kwargs)`` → path relativo al bucket root
- ``gs_url(bucket_key, pattern_key, **kwargs)`` → URL ``gs://bucket/path``
- ``https_url(bucket_key, pattern_key, **kwargs)`` → URL pubblico GCS
- ``get_bucket(bucket_key)`` → nome bucket per chiave
- Costanti ``CLEAN_BUCKET``, ``MART_BUCKET``

Esempio::

    from lab_connectors.gcs.paths import resolve, gs_url

    # Path relativo
    resolve("clean_parquet", slug="ispra_ru_base", year=2024)
    # → "ispra_ru_base/2024/ispra_ru_base_2024_clean.parquet"

    # URL completo gs://
    gs_url("clean", "clean_parquet", slug="ispra_ru_base", year=2024)
    # → "gs://dataciviclab-clean/ispra_ru_base/2024/ispra_ru_base_2024_clean.parquet"

I pattern canonici sono definiti in ``paths.json`` e coprono tutti gli artifact
prodotti dalla pipeline. Se aggiungi un nuovo pattern, aggiorna entrambi i file.
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
    """Carica il contratto paths.json (lazy, thread-safe)."""
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
                "Verifica che lab-connectors sia installato con i data file "
                "(controlla MANIFEST.in o pyproject.toml include)."
            ) from None
        return _CONTRACT


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_bucket(bucket_key: str) -> str:
    """Restituisce il nome bucket per una chiave (es. ``clean``, ``mart``).

    Raises:
        KeyError: se la chiave non esiste nel contratto.

    """
    buckets = load_contract()["buckets"]
    if bucket_key not in buckets:
        raise KeyError(
            f"Bucket key sconosciuta: {bucket_key!r}. "
            f"Disponibili: {list(buckets)}"
        )
    return buckets[bucket_key]


def get_pattern(pattern_key: str) -> str:
    """Restituisce il template string di un pattern.

    Raises:
        KeyError: se il pattern non esiste nel contratto.

    """
    patterns = load_contract()["patterns"]
    if pattern_key not in patterns:
        raise KeyError(
            f"Pattern sconosciuto: {pattern_key!r}. "
            f"Disponibili: {list(patterns)}"
        )
    return patterns[pattern_key]


def resolve(pattern_key: str, **kwargs: Any) -> str:
    """Risolve un pattern con i parametri forniti.

    Ritorna il path **relativo al bucket root** (senza protocollo ne bucket).

    Esempi::

        resolve("clean_parquet", slug="ispra_ru_base", year=2024)
        # → "ispra_ru_base/2024/ispra_ru_base_2024_clean.parquet"

        resolve("catalog_manifest")
        # → "catalog/manifest.json"

    Raises:
        KeyError: se il pattern non esiste.
        KeyError: se manca un parametro obbligatorio del template.

    """
    template = get_pattern(pattern_key)
    try:
        return template.format(**kwargs)
    except KeyError as e:
        raise KeyError(
            f"Parametro mancante per il pattern {pattern_key!r}: {e}. "
            f"Il template è: {template!r}"
        ) from None


def gs_url(bucket_key: str, pattern_key: str, **kwargs: Any) -> str:
    """Compone un URL ``gs://<bucket>/<path>``.

    Args:
        bucket_key: chiave bucket (es. ``clean``, ``mart``).
        pattern_key: chiave pattern (es. ``clean_parquet``).
        **kwargs: parametri per il pattern.

    Esempio::

        gs_url("clean", "clean_parquet", slug="ispra_ru_base", year=2024)
        # → "gs://dataciviclab-clean/ispra_ru_base/2024/ispra_ru_base_2024_clean.parquet"

    """
    bucket = get_bucket(bucket_key)
    path = resolve(pattern_key, **kwargs)
    return f"gs://{bucket}/{path}"


def https_url(bucket_key: str, pattern_key: str, **kwargs: Any) -> str:
    """Compone un URL HTTPS pubblico GCS.

    Args:
        bucket_key: chiave bucket (es. ``clean``, ``mart``).
        pattern_key: chiave pattern (es. ``clean_parquet``).
        **kwargs: parametri per il pattern.

    Esempio::

        https_url("clean", "clean_parquet", slug="ispra_ru_base", year=2024)
        # → "https://storage.googleapis.com/dataciviclab-clean/ispra_ru_base/2024/...parquet"

    """
    bucket = get_bucket(bucket_key)
    path = resolve(pattern_key, **kwargs)
    return f"https://storage.googleapis.com/{bucket}/{path}"


# ---------------------------------------------------------------------------
# Costanti di comodo (bucket names)
# ---------------------------------------------------------------------------

CLEAN_BUCKET: str = "dataciviclab-clean"
MART_BUCKET: str = "dataciviclab-mart"


def _init_bucket_constants() -> None:
    """Aggiorna le costanti dai valori reali del contratto."""
    global CLEAN_BUCKET, MART_BUCKET
    try:
        contract = load_contract()
        CLEAN_BUCKET = contract["buckets"]["clean"]
        MART_BUCKET = contract["buckets"]["mart"]
    except (RuntimeError, KeyError):
        pass  # mantieni i default hardcoded


_init_bucket_constants()


# ---------------------------------------------------------------------------
# Convenience functions per i pattern più comuni
# ---------------------------------------------------------------------------

def clean_parquet(slug: str, year: int | str) -> str:
    """Path relativo per un clean parquet: ``{slug}/{year}/{slug}_{year}_clean.parquet``.

    Returns:
        Path relativo al bucket root.

    Esempio::

        clean_parquet("ispra_ru_base", 2024)
        # → "ispra_ru_base/2024/ispra_ru_base_2024_clean.parquet"

    """
    return resolve("clean_parquet", slug=slug, year=str(year))


def pipeline_run(slug: str, year: int | str) -> str:
    """Path relativo per pipeline_run.json."""
    return resolve("pipeline_run", slug=slug, year=str(year))


def catalog_manifest() -> str:
    """Path relativo per catalog/manifest.json."""
    return resolve("catalog_manifest")


__all__ = [
    "load_contract",
    "get_bucket",
    "get_pattern",
    "resolve",
    "gs_url",
    "https_url",
    "CLEAN_BUCKET",
    "MART_BUCKET",
    "clean_parquet",
    "pipeline_run",
    "catalog_manifest",
]
