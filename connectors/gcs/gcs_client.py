from __future__ import annotations

import os
from typing import Any

import httpx
from google.api_core.exceptions import Forbidden, GoogleAPICallError, NotFound
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import storage


TIMEOUT_SECONDS = 10
DEFAULT_WARMUP_BUCKET = os.environ.get("GCS_WARMUP_BUCKET", "").strip()


class GcsClientError(RuntimeError):
    pass


def _make_storage_client() -> storage.Client:
    try:
        return storage.Client()
    except DefaultCredentialsError as exc:
        raise GcsClientError(
            "Application Default Credentials non trovate. Eseguire `gcloud auth application-default login`."
        ) from exc


try:
    _client = _make_storage_client()
except GcsClientError:
    _client = None


def warmup() -> None:
    """Scalda la connessione HTTP verso GCS per rendere piu' veloce la prima chiamata."""
    try:
        if _client is not None and DEFAULT_WARMUP_BUCKET:
            next(iter(_client.list_blobs(DEFAULT_WARMUP_BUCKET, max_results=1)), None)
    except Exception:
        pass


def list_objects(
    bucket: str,
    prefix: str | None = None,
    limit: int | None = None,
    page_token: str | None = None,
) -> dict[str, Any]:
    bucket_name = (bucket or "").strip()
    if not bucket_name:
        raise GcsClientError("bucket vuoto")

    safe_limit = max(1, limit) if limit is not None else None
    safe_prefix = (prefix or "").strip() or None
    try:
        client = _client or _make_storage_client()
        blobs_iter = client.list_blobs(bucket_name, prefix=safe_prefix)
        if page_token:
            blobs_iter.page_token = page_token
        if safe_limit:
            blobs_iter.max_results = safe_limit

        objects = []
        next_page_token = None
        for blob in blobs_iter:
            objects.append(
                {
                    "name": blob.name,
                    "size": int(blob.size or 0),
                    "updated": blob.updated.isoformat() if blob.updated else None,
                    "public_url": f"https://storage.googleapis.com/{bucket_name}/{blob.name}",
                }
            )
            if safe_limit and len(objects) >= safe_limit:
                break

        # Check if there are more pages
        try:
            next_page_token = blobs_iter.next_page_token
        except Exception:
            pass

    except Forbidden as exc:
        raise GcsClientError(
            f"Accesso negato al bucket `{bucket_name}` con le ADC correnti."
        ) from exc
    except NotFound as exc:
        raise GcsClientError(f"Bucket `{bucket_name}` non trovato.") from exc
    except GoogleAPICallError as exc:
        raise GcsClientError(f"Errore GCS su `{bucket_name}`: {exc}") from exc

    result = {
        "bucket": bucket_name,
        "prefix": safe_prefix,
        "count": len(objects),
        "objects": objects,
    }
    if safe_limit is not None:
        result["limit"] = safe_limit
        result["next_page_token"] = next_page_token if next_page_token else None
    return result


def check_public(url: str) -> dict[str, Any]:
    target_url = (url or "").strip()
    if not target_url:
        raise GcsClientError("url vuoto")

    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
            resp = client.head(target_url)
            if resp.status_code in (405, 501):
                resp = client.get(target_url, headers={"Range": "bytes=0-0"})
    except httpx.TimeoutException as exc:
        raise GcsClientError(f"Timeout su `{target_url}`.") from exc
    except httpx.HTTPError as exc:
        raise GcsClientError(f"Errore HTTP su `{target_url}`: {exc}") from exc

    return {
        "url": target_url,
        "accessible": resp.status_code == 200 or resp.status_code == 206,
        "status_code": resp.status_code,
        "content_type": resp.headers.get("content-type"),
    }
