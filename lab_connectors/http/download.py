"""Funzione standalone download(url) -> bytes.

Wrapper per script che vogliono scaricare dati senza istanziare HttpClient.
Usa internamente la catena di fallback completa di HttpClient
(TLS 1.2 → verify=False → proxy → curl → urllib, già in #67).

Il proxy (``BLOCKED_SOURCE_PROXY``) è gestito automaticamente da
``HttpClient`` come fallback su 403/407/timeout — ``download()``
non lo forza mai al primo tentativo.
"""

from __future__ import annotations

from lab_connectors.http import HttpClient


def download(
    url: str,
    *,
    timeout: int = 60,
    user_agent: str | None = None,
    max_retries: int = 2,
) -> bytes:
    """Scarica un URL con HttpClient, gestisce retry/proxy/SSL.

    Wrapper standalone per script che vogliono scaricare dati senza
    istanziare HttpClient. Usa internamente la catena di fallback
    completa (TLS 1.2 → verify=False → proxy → curl → urllib).

    Il proxy ``BLOCKED_SOURCE_PROXY`` (se configurato) viene usato
    automaticamente da HttpClient come fallback — mai forzato al
    primo tentativo.

    Args:
        url: URL da scaricare.
        timeout: Timeout secondi per tentativo.
        user_agent: Custom User-Agent.
        max_retries: Tentativi totali (default 2 = 1 tentativo + 1 retry).

    Returns:
        bytes del contenuto scaricato.

    Raises:
        RuntimeError: se il download fallisce dopo tutti i tentativi.
        ValueError: se URL è vuoto o malformato.

    """
    if not url:
        raise ValueError("URL cannot be empty")

    client = HttpClient(
        timeout=timeout,
        max_retries=max_retries,
        user_agent=user_agent or None,
    )

    result = client.get(url)
    if result.is_ok and result.response is not None and result.response.status_code < 400:
        return result.response.content

    status = result.response.status_code if result.response else "no response"
    err = str(result.err) if result.err else f"HTTP {status}"
    raise RuntimeError(f"Download failed for {url}: {err}")
