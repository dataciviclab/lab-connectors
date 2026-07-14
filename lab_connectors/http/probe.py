"""HTTP probe utilities: reachability, headers, content sniffing.

Centralizzato in lab-connectors per evitare duplicazione con toolkit/scout/http.py.
Tutte le funzioni usano HttpClient (con retry, proxy, fallback) invece di loop custom.
"""

from __future__ import annotations

from typing import Any

from lab_connectors.http import HttpClient

PROBE_TIMEOUT = 30
"""Timeout di default per probe leggeri (HEAD/GET Range)."""


def probe_url_headers(
    url: str,
    *,
    timeout: int = PROBE_TIMEOUT,
    user_agent: str = "dataciviclab-probe/1.0",
    client: HttpClient | None = None,
) -> dict[str, Any]:
    """HEAD + GET Range fallback. Ritorna header info + reachability.

    Usa HttpClient con un solo livello di retry (quello di HttpClient,
    non un loop aggiuntivo). Se il server non supporta HEAD, ripiega su
    GET con Range: bytes=0-0 (streaming, non scarica l'intero file).

    Args:
        url: URL da probe.
        timeout: Timeout HTTP per il client.
        user_agent: User-Agent.
        client: HttpClient opzionale. Se fornito, lo usa invece di crearne uno.

    Returns:
        dict con chiavi: requested_url, final_url, status_code, content_type,
        content_disposition, content_length, method.

    Raises:
        RuntimeError: se HEAD + GET Range falliscono tutti.

    """
    client = client or HttpClient(timeout=timeout, user_agent=user_agent, max_retries=2)

    def _build(
        *,
        status_code: int,
        content_type: str | None,
        content_disposition: str | None,
        content_length: int | None = None,
        final_url: str,
        method: str,
    ) -> dict[str, Any]:
        return {
            "requested_url": url,
            "final_url": final_url,
            "status_code": status_code,
            "content_type": content_type,
            "content_disposition": content_disposition,
            "content_length": content_length,
            "method": method,
        }

    # Tentativo HEAD
    head_result = client.head(url)
    if (
        head_result.is_ok
        and head_result.response is not None
        and head_result.response.status_code < 500
    ):
        resp = head_result.response
        ct_len = resp.headers.get("Content-Length")
        return _build(
            status_code=resp.status_code,
            content_type=resp.headers.get("Content-Type"),
            content_disposition=resp.headers.get("Content-Disposition"),
            content_length=int(ct_len) if ct_len and ct_len.isdigit() else None,
            final_url=resp.url,
            method="head",
        )

    # HEAD fallito → GET con Range: bytes=0-0 (stream=True)
    range_result = client.get(url, headers={"Range": "bytes=0-0"}, stream=True)
    if range_result.is_ok and range_result.response is not None:
        resp = range_result.response
        if resp.status_code == 206:
            cr = resp.headers.get("Content-Range", "")
            file_size = (
                int(cr.split("/")[-1].strip())
                if cr and "/" in cr and cr.split("/")[-1].strip().isdigit()
                else None
            )
        else:
            ct_len = resp.headers.get("Content-Length")
            file_size = int(ct_len) if ct_len and ct_len.isdigit() else None
        getattr(resp, "close", lambda: None)()
        return _build(
            status_code=resp.status_code,
            content_type=resp.headers.get("Content-Type"),
            content_disposition=resp.headers.get("Content-Disposition"),
            content_length=file_size,
            final_url=resp.url,
            method="get_range",
        )

    # HTTP → HTTPS fallback (per URL senz'ansa che puntano a server HTTPS)
    if url.startswith("http://"):
        https_url = "https://" + url[7:]
        fb_client = HttpClient(timeout=timeout, user_agent=user_agent, max_retries=2)
        return probe_url_headers(
            https_url, timeout=timeout, user_agent=user_agent, client=fb_client
        )

    raise RuntimeError(f"HEAD failed for {url}")
