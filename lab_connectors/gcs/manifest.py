"""Manifest GCS: indice centralizzato di tutti i file sui bucket pubblici.

Generato periodicamente da scripts/scan_gcs_manifest.py e pubblicato su
gs://dataciviclab-clean/registry/gcs_manifest.json.

Qualsiasi repo del Lab può leggere il manifest per avere la lista completa
dei file senza chiamate GCS live.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from lab_connectors.gcs.client import list_objects, upload_string
from lab_connectors.gcs.paths import CLEAN_BUCKET, MART_BUCKET

MANIFEST_PATH = "registry/gcs_manifest.json"
MANIFEST_URL = f"https://storage.googleapis.com/{CLEAN_BUCKET}/{MANIFEST_PATH}"
SCAN_BUCKETS = [CLEAN_BUCKET, MART_BUCKET]


def build_manifest() -> dict[str, Any]:
    """Scandisce i bucket pubblici e produce il manifest completo.

    Returns:
        Dict con: generated_at, buckets, file_count, total_size_bytes, files.
        Ogni file: { url (s3://), slug, bucket, year, path, size_bytes, updated }.

    """
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
    """Carica il manifest su GCS (richiede SDK autenticato)."""
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

    """
    from urllib.error import HTTPError
    from urllib.request import urlopen

    fetch_url = url or MANIFEST_URL
    try:
        with urlopen(fetch_url, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        if e.code in (404, 403):
            raise FileNotFoundError(f"Manifest non trovato a {fetch_url} (HTTP {e.code})") from e
        raise RuntimeError(f"Errore HTTP {e.code} per manifest a {fetch_url}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"Manifest corrotto a {fetch_url}: {e}") from e
    except TimeoutError as e:
        raise TimeoutError(f"Timeout lettura manifest da {fetch_url}") from e
