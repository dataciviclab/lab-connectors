"""Testing utilities for DataCivicLab connectors.

Provides ``FakeHttpClient`` — a drop-in replacement for ``HttpClient``
that returns pre-configured responses without making real HTTP calls.

Usage::

    from lab_connectors.testing import FakeHttpClient

    fake = FakeHttpClient()
    fake.responses["https://example.com/data.csv"] = HttpResult(
        response=response_stub, err=None
    )
    result = fake.get("https://example.com/data.csv")
    assert result.is_ok
"""
from __future__ import annotations

import typing
from collections.abc import Callable
from typing import Any

import requests

from lab_connectors.http.types import HttpResult

if typing.TYPE_CHECKING:
    import requests

_ResponseOrCallable = HttpResult | Callable[..., HttpResult]


class FakeHttpClient:
    """Fake HTTP client that returns pre-configured responses.

    Mirrors the interface of ``lab_connectors.http.HttpClient`` without
    making any real network calls. Useful for unit tests where you want
    to control what each URL returns.

    Register responses via the ``responses`` dict before calling methods::

        fake = FakeHttpClient()
        fake.responses["https://example.com/ok"] = HttpResult(
            response=_fake_response(200), err=None
        )
        result = fake.get("https://example.com/ok")
        assert result.is_ok

    If a registered value is a callable, it is invoked with
    ``(url, **kwargs)`` and must return an ``HttpResult``.
    """

    DEFAULT_TIMEOUT_SECONDS = 60
    DEFAULT_USER_AGENT = "DataCivicLab-FakeHttpClient/0.1"

    def __init__(
        self,
        timeout: int | float | tuple[int, int] = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
        retry_backoff: float = 1.0,
        user_agent: str | None = None,
    ):
        """Initialize the fake HTTP client.

        Args:
            timeout: Ignored (compatibility with ``HttpClient``).
            max_retries: Ignored (compatibility).
            retry_backoff: Ignored (compatibility).
            user_agent: Ignored (compatibility).

        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT

        #: Map URL -> HttpResult or callable(url, **kwargs) -> HttpResult.
        self.responses: dict[str, _ResponseOrCallable] = {}

        #: Log of all requests made through this client.
        #: Each entry is (method, url, kwargs_dict).
        self.requests: list[tuple[str, str, dict[str, Any]]] = []

    # ------------------------------------------------------------------
    # Public methods matching HttpClient
    # ------------------------------------------------------------------

    def get(self, url: str, **kwargs: Any) -> HttpResult:
        """Simulate a GET request — returns pre-registered response."""
        self.requests.append(("GET", url, kwargs))
        return self._resolve(url, **kwargs)

    def head(self, url: str, **kwargs: Any) -> HttpResult:
        """Simulate a HEAD request — returns pre-registered response."""
        self.requests.append(("HEAD", url, kwargs))
        return self._resolve(url, **kwargs)

    def post(
        self,
        url: str,
        data: Any = None,
        json: Any = None,
        *,
        retries: int = 0,
        **kwargs: Any,
    ) -> HttpResult:
        """Simulate a POST request — returns pre-registered response."""
        self.requests.append(
            ("POST", url, {"data": data, "json": json, "retries": retries, **kwargs})
        )
        return self._resolve(url, data=data, json=json, **kwargs)

    def close(self) -> None:
        """No-op. Compatible with HttpClient.close()."""

    def __enter__(self) -> FakeHttpClient:
        """Enter context manager — returns self (no-op)."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Exit context manager — calls close() (no-op)."""
        self.close()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve(self, url: str, **kwargs: Any) -> HttpResult:
        """Return pre-configured response for *url*."""
        entry = self.responses.get(url)
        if entry is None:
            raise KeyError(
                f"No response registered for {url!r}. "
                f"Registered URLs: {list(self.responses)}"
            )
        if callable(entry):
            return entry(url, **kwargs)
        return entry


# ------------------------------------------------------------------
# Convenience factory helpers
# ------------------------------------------------------------------


def fake_response(
    status_code: int = 200,
    text: str = "",
    json_data: object = None,
    headers: dict[str, str] | None = None,
) -> _FakeResponse:
    """Build a ``requests.Response``-like stub for use with ``HttpResult``.

    The returned object exposes the minimum surface that ``HttpResult``
    and downstream code rely on:
    ``status_code``, ``text``, ``.json()``, ``.raise_for_status()``.

    Example::

        result = HttpResult(
            response=fake_response(200, "hello"),
            err=None,
        )
    """
    return _FakeResponse(
        status_code=status_code,
        text=text,
        json_data=json_data,
        headers=headers,
    )


class _FakeResponse:
    """Minimal ``requests.Response`` stub for testing."""

    def __init__(
        self,
        status_code: int = 200,
        text: str = "",
        json_data: object = None,
        headers: dict[str, str] | None = None,
    ):
        """Initialize the response stub.

        Args:
            status_code: HTTP status code.
            text: Response body as text (``.content`` derived from it).
            json_data: Optional parsed JSON for ``.json()``.
            headers: Response headers dict.

        """
        self.status_code = status_code
        self._text = text
        self._json_data = json_data
        self.headers = headers or {}
        self.ok = 200 <= status_code < 300
        self.url = ""  # set by caller if needed
        self.reason: str | None = None

    @property
    def text(self) -> str:
        return self._text

    @text.setter
    def text(self, value: str) -> None:
        self._text = value

    @property
    def content(self) -> bytes:
        """Bytes content — derived from ``text`` (utf-8 encoded).

        Matches ``requests.Response.content`` for code that reads
        binary payloads (e.g. ``HttpFileSource.fetch``).
        """
        return self._text.encode("utf-8")

    def json(self) -> object:
        if self._json_data is not None:
            return self._json_data
        import json as _json

        return _json.loads(self.text)

    def raise_for_status(self) -> None:
        if not self.ok:
            raise _FakeHTTPError(self.status_code, self.text, response=self)

    def __enter__(self) -> _FakeResponse:
        """Enter context manager — returns self (no-op)."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Exit context manager — no-op."""

    def __repr__(self) -> str:
        return f"<_FakeResponse [{self.status_code}]>"


class _FakeHTTPError(requests.HTTPError):
    """Mimics ``requests.HTTPError`` — fully compatible subclass.

    Usage::

        raise _FakeHTTPError(404, "not found", response=some_response)

    Code that catches ``requests.HTTPError`` (via ``isinstance``) and
    accesses ``e.response`` will get the provided response object.
    """

    def __init__(self, status_code: int, text: str = "",
                 response: Any = None):
        """Initialize the HTTP error.

        Args:
            status_code: HTTP status code.
            text: Response body (truncated for the message).
            response: The response object (``_FakeResponse``) that caused the error.

        """
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}: {text[:50]}",
                         response=response)
