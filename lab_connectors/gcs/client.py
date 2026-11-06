"""Unified GCS client for DataCivicLab.

Supporta 3 modalità:
  - auth=None (auto): prova SDK google.cloud.storage, fallback HTTP API
  - auth=True: richiede SDK autenticato (upload, list privati)
  - auth=False: solo HTTP API (nessuna dipendenza SDK)

Le funzioni module-level usano un client singleton lazy.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Client singleton
# ---------------------------------------------------------------------------

_GCS_CLIENT: Any | None = None  # storage.Client instance (lazy)
_GCS_AUTH_MODE: str | None = None  # "sdk" | "http" | None
_GCS_LOCK = threading.Lock()


def _get_storage_client(project: str = "dataciviclab") -> Any | None:
    """Lazy init del SDK google.cloud.storage.

    Ritorna None se il pacchetto non è installato o le credenziali mancano.
    """
    global _GCS_CLIENT, _GCS_AUTH_MODE
    with _GCS_LOCK:
        if _GCS_AUTH_MODE == "http":
            return None  # già fallito, non riprovare
        if _GCS_CLIENT is not None:
            return _GCS_CLIENT

        try:
            from google.cloud import storage
        except ImportError:
            _GCS_AUTH_MODE = "http"
            return None

        try:
            _GCS_CLIENT = storage.Client(project=project)
            _GCS_AUTH_MODE = "sdk"
            return _GCS_CLIENT
        except Exception:
            _GCS_AUTH_MODE = "http"
            return None


# ---------------------------------------------------------------------------
# HTTP API helpers (nessuna dipendenza SDK)
# ---------------------------------------------------------------------------


def _http_get_json(url: str, *, timeout: int = 30) -> dict[str, Any]:
    """GET JSON via ``HttpClient`` (retry, SSL fallback, UA uniforme)."""
    from lab_connectors.http import HttpClient

    result = HttpClient(timeout=timeout, max_retries=2).get(url)
    resp = result.response
    if resp is None or resp.status_code >= 400:
        status = resp.status_code if resp is not None else "no response"
        raise RuntimeError(f"GCS HTTP error {status} per {url} ({result.err})")
    payload = resp.json()
    if not isinstance(payload, dict):
        raise TypeError(f"Risposta GCS non valida (non oggetto JSON): {url}")
    return payload


def _http_head(url: str, *, timeout: int = 30) -> int | None:
    """HEAD via ``HttpClient``. Status code o ``None`` su errore."""
    from lab_connectors.http import HttpClient

    result = HttpClient(timeout=timeout, max_retries=1).head(url)
    if result.response is None:
        return None
    return result.response.status_code


def _gcs_http_list(
    bucket: str,
    prefix: str = "",
    limit: int | None = None,
    page_token: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """List objects via HTTP API. Returns (items, next_page_token)."""
    from urllib.parse import quote, urlencode

    params: dict[str, str | int] = {
        "prefix": prefix,
        "fields": "items(name,size,updated),nextPageToken",
    }
    if limit is not None:
        params["maxResults"] = limit
    if page_token:
        params["pageToken"] = page_token

    url = f"https://storage.googleapis.com/storage/v1/b/{quote(bucket)}/o?{urlencode(params)}"
    payload = _http_get_json(url)

    items = payload.get("items", [])
    next_token = payload.get("nextPageToken")
    return items, next_token


def _gcs_http_head(bucket: str, key: str) -> int | None:
    """HEAD request a un oggetto GCS. Ritorna status code o None su errore."""
    from urllib.parse import quote

    url = f"https://storage.googleapis.com/{quote(bucket, safe='')}/{quote(key, safe='/_-.')}"
    try:
        return _http_head(url)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_objects(
    bucket: str,
    prefix: str = "",
    limit: int | None = None,
    page_token: str | None = None,
    auth: bool | None = None,
) -> list[dict[str, Any]]:
    """List oggetti in un bucket GCS.

    Args:
        bucket: Nome bucket.
        prefix: Filtro prefisso.
        limit: Massimo risultati (default: nessun limite).
        page_token: Token di paginazione per continuation.
        auth: True=SDK obbligatorio, False=HTTP API, None=auto.

    Returns:
        Lista di dict con chiavi name, size, updated.

    Raises:
        RuntimeError: Se auth=True ma SDK/creds non disponibili.

    """
    # auth=True richiede SDK — mai fallback HTTP
    if auth is True:
        client = _get_storage_client()
        if client is None:
            raise RuntimeError(
                "auth=True ma google.cloud.storage non disponibile o credenziali mancanti."
            )
        from google.cloud.storage.retry import DEFAULT_RETRY

        blobs = list(
            client.list_blobs(
                bucket,
                prefix=prefix,
                max_results=limit,
                page_token=page_token,
                retry=DEFAULT_RETRY,
            )
        )
        return [
            {
                "name": b.name,
                "size": b.size,
                "updated": b.updated.isoformat() if b.updated else None,
            }
            for b in blobs
        ]

    # auth=False: solo HTTP API, niente SDK (paginazione completa)
    if auth is False:
        all_items: list[dict[str, Any]] = []
        next_token = page_token
        remaining = limit
        while True:
            page_limit = remaining if remaining is not None else None
            page_items, next_token = _gcs_http_list(bucket, prefix, page_limit, next_token)
            for item in page_items:
                all_items.append(
                    {
                        "name": item["name"],
                        "size": int(item.get("size", 0)),
                        "updated": item.get("updated"),
                    }
                )
                if remaining is not None:
                    remaining -= 1
                    if remaining <= 0:
                        return all_items
            if not next_token:
                break
        return all_items

    # auth=None (auto): prova SDK, fallback HTTP con paginazione completa
    client = _get_storage_client()
    if client is not None:
        from google.cloud.storage.retry import DEFAULT_RETRY

        blobs = list(
            client.list_blobs(
                bucket,
                prefix=prefix,
                max_results=limit,
                page_token=page_token,
                retry=DEFAULT_RETRY,
            )
        )
        return [
            {
                "name": b.name,
                "size": b.size,
                "updated": b.updated.isoformat() if b.updated else None,
            }
            for b in blobs
        ]

    # Fallback HTTP con paginazione
    all_items = []
    token = page_token
    remaining = limit
    while True:
        page_limit = min(remaining, 1000) if remaining is not None else None
        items, next_token = _gcs_http_list(bucket, prefix, page_limit, token)
        for item in items:
            all_items.append(
                {
                    "name": item["name"],
                    "size": int(item.get("size", 0)),
                    "updated": item.get("updated"),
                }
            )
            if remaining is not None:
                remaining -= 1
                if remaining <= 0:
                    return all_items
        if not next_token:
            break
        token = next_token

    return all_items


def object_exists(bucket: str, key: str) -> bool:
    """Verifica se un oggetto esiste in un bucket tramite HEAD pubblico."""
    status = _gcs_http_head(bucket, key)
    return status is not None and status < 400


def check_public(url: str) -> dict[str, Any]:
    """Verifica se un URL pubblico GCS è raggiungibile.

    Delega a ``lab_connectors.http.probe.probe_url_headers`` (HEAD + fallback
    GET Range), così la logica di probe resta una sola nel Lab.

    Returns:
        dict con chiavi: accessible (bool), status_code (int|None),
        content_type (str|None)

    """
    from lab_connectors.http.probe import probe_url_headers

    try:
        info = probe_url_headers(url, timeout=30)
    except RuntimeError:
        return {"accessible": False, "status_code": None, "content_type": None}

    status = info.get("status_code")
    return {
        "accessible": status is not None and int(status) < 400,
        "status_code": status,
        "content_type": info.get("content_type"),
    }


def upload_file(local_path: str | Path, bucket: str, gcs_path: str) -> None:
    """Carica un file locale su GCS. Richiede SDK autenticato."""
    client = _get_storage_client()
    if client is None:
        raise RuntimeError(
            "GCS upload richiede google.cloud.storage installato e "
            "Application Default Credentials configurate."
        )

    bucket_obj = client.bucket(bucket)
    blob = bucket_obj.blob(gcs_path)
    blob.upload_from_filename(str(local_path))


def upload_string(
    content: str,
    bucket: str,
    gcs_path: str,
    content_type: str | None = None,
) -> None:
    """Carica una stringa su GCS. Richiede SDK autenticato."""
    client = _get_storage_client()
    if client is None:
        raise RuntimeError(
            "GCS upload richiede google.cloud.storage installato e "
            "Application Default Credentials configurate."
        )

    bucket_obj = client.bucket(bucket)
    blob = bucket_obj.blob(gcs_path)
    kwargs: dict[str, str] = {}
    if content_type:
        kwargs["content_type"] = content_type
    blob.upload_from_string(content, **kwargs)
