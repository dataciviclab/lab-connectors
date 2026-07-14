"""Funzione standalone download(url) -> bytes.

Wrapper per script che vogliono scaricare dati senza istanziare HttpClient.
Usa internamente la catena di fallback completa di HttpClient
(TLS 1.2 → verify=False → proxy → curl → urllib, già in #67).
"""

from __future__ import annotations

import os
from typing import Any

from lab_connectors.http import HttpClient


def download(
    url: str,
    *,
    timeout: int = 60,
    user_agent: str | None = None,
    proxy_from_env: bool = True,
    max_retries: int = 2,
) -> bytes:
    """Scarica un URL con HttpClient, gestisce retry/proxy/SSL.

    Wrapper standalone per script che vogliono scaricare dati senza
    istanziare HttpClient. Usa internamente la catena di fallback
    completa (TLS 1.2 → verify=False → proxy → curl → urllib).

    Args:
        url: URL da scaricare.
        timeout: Timeout secondi per tentativo.
        user_agent: Custom User-Agent.
        proxy_from_env: Se True, usa ``BLOCKED_SOURCE_PROXY`` se settata.
        max_retries: Tentativi totali (default 2 = 1 tentativo + 1 retry).

    Returns:
        bytes del contenuto scaricato.

    Raises:
        RuntimeError: se il download fallisce dopo tutti i tentativi.
        ValueError: se URL è vuoto o malformato.

    """
    if not url:
        raise ValueError("URL cannot be empty")

    proxies: dict[str, str] | None = None
    if proxy_from_env:
        proxy_url = os.environ.get("BLOCKED_SOURCE_PROXY")
        if proxy_url:
            proxies = {"http": proxy_url, "https": proxy_url}

    client = HttpClient(
        timeout=timeout,
        max_retries=max_retries,
        user_agent=user_agent or None,
    )

    kwargs: dict[str, Any] = {}
    if proxies:
        kwargs["proxies"] = proxies
    result = client.get(url, **kwargs)

    if result.is_ok and result.response is not None and result.response.status_code < 400:
        return result.response.content

    status = result.response.status_code if result.response else "no response"
    err = str(result.err) if result.err else f"HTTP {status}"
    raise RuntimeError(f"Download failed for {url}: {err}")
