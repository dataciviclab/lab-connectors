"""Manifest GCS: indice centralizzato di tutti i file sui bucket pubblici.

Generato periodicamente da scripts/scan_gcs_manifest.py e pubblicato su
gs://dataciviclab-clean/registry/gcs_manifest.json.

.. deprecated::
    In dismissione: è stato sostituito dai ``registry.json`` dei repo per la
    risoluzione degli artifact e, per l'esistenza dei file, da
    ``gcs.paths.location_urls()`` / ``gcs.client.object_exists``.
    L'unico consumer (``data-explorer``) migrerà a ``location_urls``; non
    usare il manifest in nuovi consumer.
"""

from __future__ import annotations

import json
import warnings
from datetime import UTC, datetime
from typing import Any

from lab_connectors.gcs.client import list_objects, upload_string
from lab_connectors.gcs.paths import CLEAN_BUCKET, MART_BUCKET

MANIFEST_PATH = "registry/gcs_manifest.json"
MANIFEST_URL = f"https://storage.googleapis.com/{CLEAN_BUCKET}/{MANIFEST_PATH}"
SCAN_BUCKETS = [CLEAN_BUCKET, MART_BUCKET]


_DEPRECATION_MSG = (
    "gcs_manifest è deprecato: usa i registry.json dei repo per gli artifact e "
    "gcs.paths.location_urls()/object_exists() per l'esistenza dei file."
)


def build_manifest() -> dict[str, Any]:
    """Scandisce i bucket pubblici e produce il manifest completo.

    .. deprecated::
        Usa i registry.json dei repo + ``location_urls()``; il manifest non ha
        più consumer nel Lab.

    Returns:
        Dict con: generated_at, buckets, file_count, total_size_bytes, files.
        Ogni file: { url (s3://), slug, bucket, year, path, size_bytes, updated }.

    """
    warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)

    files: list[dict[str, Any]] = []
    total_size = 0

    for bucket in SCAN_BUCKETS:
        objects = list_objects(bucket, auth=False)
        for obj in objects:
            name: str = obj["name"]
            size = obj.get("size", 0)
            total_size += size

            # Estrai slug e anno dal path (pattern: slug/anno/file)
            parts = name.split("/")
            slug = parts[0] if len(parts) >= 1 else None
            year = None
            for p in parts:
                if p.isdigit() and len(p) == 4:
                    year = int(p)
                    break

            files.append(
                {
                    "url": f"s3://{bucket}/{name}",
                    "slug": slug,
                    "bucket": bucket,
                    "year": year,
                    "path": name,
                    "size_bytes": size,
                    "updated": obj.get("updated"),
                }
            )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "file_count": len(files),
        "total_size_bytes": total_size,
        "buckets": SCAN_BUCKETS,
        "files": files,
    }


def upload_manifest(manifest: dict[str, Any]) -> None:
    """Carica il manifest su GCS (richiede SDK autenticato).

    .. deprecated::
        Il manifest è in dismissione: nessun consumer nel Lab.
    """
    warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
    content = json.dumps(manifest, indent=2, ensure_ascii=False)
    upload_string(content, CLEAN_BUCKET, MANIFEST_PATH, content_type="application/json")


def read_manifest(url: str | None = None) -> dict[str, Any]:
    """Legge il manifest pubblico da GCS via HTTPS.

    Args:
        url: URL del manifest (default: da CLEAN_BUCKET).

    Returns:
        Dict con generated_at, file_count, total_size_bytes, files.

    Raises:
        FileNotFoundError: se il manifest non è raggiungibile (404/403).
        ValueError: se il JSON è malformato.
        TimeoutError: se la richiesta scade.

    .. deprecated::
        Usa i registry.json dei repo + ``location_urls()``.

    """
    warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
    fetch_url = url or MANIFEST_URL
    status, text = _fetch(fetch_url)

    if status in (404, 403):
        raise FileNotFoundError(f"Manifest non trovato a {fetch_url} (HTTP {status})")
    if status >= 400:
        raise RuntimeError(f"Errore HTTP {status} per manifest a {fetch_url}")

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Manifest corrotto a {fetch_url}: {e}") from e


def _fetch(url: str, *, timeout: int = 15) -> tuple[int, str]:
    """GET del manifest via ``HttpClient`` (retry, SSL fallback).

    Returns:
        (status_code, body).

    Raises:
        TimeoutError: se la richiesta scade.
        RuntimeError: se non c'è risposta per altri motivi.

    """
    from lab_connectors.http import HttpClient

    result = HttpClient(timeout=timeout, max_retries=2).get(url)
    resp = result.response
    if resp is None:
        err = result.err
        if isinstance(err, TimeoutError) or "timeout" in str(err).lower():
            raise TimeoutError(f"Timeout lettura manifest da {url}")
        raise RuntimeError(f"Manifest non raggiungibile a {url}: {err}")
    return resp.status_code, resp.text
