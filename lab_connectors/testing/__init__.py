"""Test helpers per HTTP mocking condivisi tra i repo del Lab.

Elimina la duplicazione di ``_FakeResponse`` reinventata in 14+ file
tra toolkit, source-observatory e agent-context-builder.

Uso::

    from lab_connectors.testing import http_ok, http_error, HttpResult

    # Successo
    result = http_ok(200, b"payload")
    assert result.is_ok

    # Errore HTTP (response presente ma status >= 400)
    result = http_ok(404, b"not found")
    assert result.is_ok  # HttpResult: response presente = "ok" dal punto di vista del client
    assert result.response.status_code == 404

    # Fallimento totale (nessuna response)
    result = http_error(ConnectionError("refused"))
    assert result.is_error
"""
from __future__ import annotations

from typing import Any

from lab_connectors.http.types import HttpFallbackError, HttpResult


class FakeResponse:
    """Minimal response stub duck-typing ``requests.Response``.

    Args:
        status_code: HTTP status code (default 200).
        content: Response body as bytes (default ``b""``).
        headers: Response headers dict.
        json_data: Pre-parsed JSON payload (returned by ``.json()``).
        text: Response body as text (alternative to content).
        url: Request URL.

    """

    def __init__(
        self,
        status_code: int = 200,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
        json_data: Any = None,
        text: str | None = None,
        url: str = "",
    ) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self._json_data = json_data
        self._text = text
        self.url = url

    def json(self) -> Any:
        """Return pre-parsed JSON payload."""
        return self._json_data

    @property
    def text(self) -> str:
        """Return text content."""
        if self._text is not None:
            return self._text
        return self.content.decode("utf-8", errors="replace")


def http_ok(
    status_code: int = 200,
    content: bytes = b"",
    headers: dict[str, str] | None = None,
    json_data: Any = None,
    text: str | None = None,
    url: str = "",
) -> HttpResult:
    """Costruisce un ``HttpResult`` di successo.

    Args:
        status_code: HTTP status code.
        content: Response body as bytes.
        headers: Response headers.
        json_data: Pre-parsed JSON payload.
        text: Response body as text.
        url: Request URL.

    Returns:
        HttpResult con response presente e err=None.

    """
    return HttpResult(
        response=FakeResponse(
            status_code=status_code,
            content=content,
            headers=headers,
            json_data=json_data,
            text=text,
            url=url,
        ),
        err=None,
    )


def http_error(
    exc: Exception | None = None,
    *,
    primary: Exception | None = None,
    fallback: Exception | None = None,
) -> HttpResult:
    """Costruisce un ``HttpResult`` di errore.

    Args:
        exc: Eccezione generica (ConnectionError, SSLError, ecc.).
        primary: Errore primario per HttpFallbackError.
        fallback: Errore fallback per HttpFallbackError.

    Returns:
        HttpResult con response=None e err impostata.

    Raises:
        ValueError: Se si passano sia ``exc`` che ``primary``/``fallback``.

    """
    if exc is not None and (primary is not None or fallback is not None):
        raise ValueError("Usare 'exc' oppure 'primary'+'fallback', non entrambi")

    if primary is not None or fallback is not None:
        err: Exception = HttpFallbackError(
            primary_error=primary or Exception("primary unknown"),
            fallback_error=fallback or Exception("fallback unknown"),
        )
    else:
        err = exc or Exception("unknown error")

    return HttpResult(response=None, err=err)
