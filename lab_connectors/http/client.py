"""HTTP client with SSL fallback, retry, backoff, and 429 handling.

This module provides a shared HTTP client used by all Lab repos.
It wraps requests with:
- Connection pooling (shared session, used for SSL fallback)
- SSL fallback (verify=False on SSLError)
- Configurable timeout and User-Agent
- Exponential backoff retry (configurable)
- 429 Retry-After handling
- HEAD, GET and POST methods
- HttpResult return type (no exceptions raised on HTTP errors)
"""
from __future__ import annotations

import datetime
import logging
import time
from collections.abc import Callable
from email.utils import parsedate_to_datetime
from typing import Any

import requests
import urllib3
from urllib3.exceptions import InsecureRequestWarning

from lab_connectors.http.types import HttpFallbackError, HttpResult

logger = logging.getLogger("lab_connectors.http")


class HttpClient:
    """HTTP client with SSL fallback, retry, and backoff.

    Usage:
        client = HttpClient(timeout=15)
        result = client.get("https://example.com/data.csv")
        if result.is_ok:
            print(result.response.status_code)
        else:
            print(f"Failed: {result.err}")

        # POST is also supported (same SSL fallback + retry pattern)
        result = client.post("https://example.com/api", data={"key": "value"})
    """

    DEFAULT_TIMEOUT_SECONDS = 60
    DEFAULT_USER_AGENT = "DataCivicLab-HttpClient/0.1"

    def __init__(
        self,
        timeout: int | float | tuple[int, int] = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
        retry_backoff: float = 1.0,
        user_agent: str | None = None,
    ):
        """Initialize HttpClient.

        Args:
            timeout: Request timeout in seconds.
            max_retries: Number of attempts on transient errors (5xx, 429,
                connection errors). Default 2 (2 total attempts: try once,
                retry once on failure).
            retry_backoff: Base delay in seconds for exponential backoff.
                Actual delay = backoff * 2^(attempt-1). Default 1.0.
            user_agent: Custom User-Agent string.

        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT

        # Shared session for SSL fallback (connection pooling)
        self._session = requests.Session()
        self._session.headers["User-Agent"] = self.user_agent

    def close(self) -> None:
        """Close the underlying session and release connection pool resources."""
        self._session.close()

    def __enter__(self) -> HttpClient:
        """Return self for use as a context manager."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Close the session when exiting the context manager."""
        self.close()

    # ------------------------------------------------------------------
    # Generic retry loop
    # ------------------------------------------------------------------

    def _execute(
        self,
        method_name: str,
        url: str,
        request_fn: Callable[..., requests.Response],
        ssl_fallback_fn: Callable[..., HttpResult],
        effective_retries: int,
        **kwargs: Any,
    ) -> HttpResult:
        """Execute an HTTP request with retry, backoff, and SSL fallback.

        Args:
            method_name: HTTP method name for logging (e.g. "HEAD", "GET").
            url: The URL to request.
            request_fn: Callable that performs the primary request.
            ssl_fallback_fn: Callable that performs the SSL fallback request.
            effective_retries: Number of total attempts (>= 1).
            **kwargs: Passed to request_fn.

        Returns:
            HttpResult with response or err.

        """
        last_err: Exception | None = None
        primary_exc: requests.exceptions.SSLError | None = None

        for attempt in range(effective_retries):
            if attempt > 0:
                time.sleep(self.retry_backoff * (2 ** (attempt - 1)))

            try:
                response = request_fn(url, timeout=self.timeout, **kwargs)
            except requests.exceptions.SSLError as exc:
                primary_exc = exc
                logger.warning(
                    "SSL error on %s %s (attempt %d) — fallback",
                    method_name, url, attempt + 1,
                )
                urllib3.disable_warnings(category=InsecureRequestWarning)
                return ssl_fallback_fn(url, primary_exc, kwargs)

            except requests.exceptions.RequestException as exc:
                last_err = exc
                if attempt < effective_retries - 1:
                    continue
                return HttpResult(response=None, err=exc, ssl_fallback_used=False)
            except Exception as exc:
                return HttpResult(response=None, err=exc, ssl_fallback_used=False)

            # 429 Retry-After
            if response.status_code == 429 and attempt < effective_retries - 1:
                retry_after = self._parse_retry_after(response)
                if retry_after is not None:
                    time.sleep(min(retry_after, 300))
                last_err = Exception("HTTP 429")
                continue

            # 5xx retry
            if response.status_code >= 500 and attempt < effective_retries - 1:
                last_err = Exception(f"HTTP {response.status_code}")
                continue

            return HttpResult(response=response, err=None, ssl_fallback_used=None)

        return HttpResult(
            response=None,
            err=last_err or Exception("Max retries exhausted"),
            ssl_fallback_used=False,
        )

    # ------------------------------------------------------------------
    # HEAD
    # ------------------------------------------------------------------

    def head(self, url: str, **kwargs: Any) -> HttpResult:
        """Send HEAD request with SSL fallback, retry, backoff and 429 handling.

        HEAD is idempotent — retries on 5xx, 429, and connection errors.

        Args:
            url: The URL to request.
            **kwargs: Passed to requests.head().

        Returns:
            HttpResult with response or err.

        """
        headers = kwargs.pop("headers", None) or {}
        headers["User-Agent"] = self.user_agent
        kwargs["headers"] = headers
        kwargs.setdefault("allow_redirects", True)

        return self._execute(
            "HEAD",
            url,
            lambda u, **kw: requests.head(u, **kw),
            lambda u, exc, kw: self._head_ssl_fallback(u, exc, kw),
            max(1, self.max_retries),
            **kwargs,
        )

    def _head_ssl_fallback(
        self,
        url: str,
        primary_exc: requests.exceptions.SSLError,
        kwargs: dict[str, Any],
    ) -> HttpResult:
        """SSL fallback for HEAD — strips allow_redirects to avoid collision."""
        fallback_kwargs = {
            k: v for k, v in kwargs.items()
            if k not in ("headers", "allow_redirects")
        }
        try:
            response = self._session.head(
                url,
                timeout=self.timeout,
                allow_redirects=True,
                verify=False,
                **fallback_kwargs,
            )
            return HttpResult(response=response, err=None, ssl_fallback_used=True)
        except requests.exceptions.RequestException as fallback_exc:
            logger.warning("Fallback HEAD also failed for %s: %s", url, fallback_exc)
            return HttpResult(
                response=None,
                err=HttpFallbackError(
                    primary_error=primary_exc, fallback_error=fallback_exc
                ),
                ssl_fallback_used=False,
            )
        except Exception as exc:
            return HttpResult(response=None, err=exc, ssl_fallback_used=False)

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------

    def get(self, url: str, **kwargs: Any) -> HttpResult:
        """Send GET request with SSL fallback, retry, backoff and 429 handling.

        Args:
            url: The URL to request.
            **kwargs: Passed to requests.get().

        Returns:
            HttpResult with response or err.

        """
        headers = kwargs.pop("headers", None) or {}
        headers["User-Agent"] = self.user_agent
        kwargs["headers"] = headers

        return self._execute(
            "GET",
            url,
            lambda u, **kw: requests.get(u, **kw),
            lambda u, exc, kw: self._get_ssl_fallback(u, exc, kw),
            max(1, self.max_retries),
            **kwargs,
        )

    def _get_ssl_fallback(
        self,
        url: str,
        primary_exc: requests.exceptions.SSLError,
        kwargs: dict[str, Any],
    ) -> HttpResult:
        """SSL fallback for GET — strips 'verify' from kwargs to avoid collision."""
        fallback_kwargs = {k: v for k, v in kwargs.items() if k != "verify"}
        try:
            response = self._session.get(
                url,
                timeout=self.timeout,
                verify=False,
                **fallback_kwargs,
            )
            return HttpResult(response=response, err=None, ssl_fallback_used=True)
        except requests.exceptions.RequestException as fallback_exc:
            logger.warning("Fallback GET also failed for %s: %s", url, fallback_exc)
            return HttpResult(
                response=None,
                err=HttpFallbackError(
                    primary_error=primary_exc, fallback_error=fallback_exc
                ),
                ssl_fallback_used=False,
            )
        except Exception as exc:
            return HttpResult(response=None, err=exc, ssl_fallback_used=False)

    # ------------------------------------------------------------------
    # POST
    # ------------------------------------------------------------------

    def post(
        self,
        url: str,
        data: Any = None,
        json: Any = None,
        *,
        retries: int = 0,
        **kwargs: Any,
    ) -> HttpResult:
        """Send POST request with SSL fallback (opt-in retry, backoff, 429).

        Unlike GET/HEAD, retry is **opt-in** (default 0) because POST
        is not idempotent. Pass ``retries=N`` for idempotent endpoints
        (file download, SPARQL query).

        Args:
            url: The URL to request.
            data: Form-encoded body.
            json: JSON-serializable body.
            retries: Number of retry attempts (default 0).
            **kwargs: Passed to ``requests.post()``.

        Returns:
            HttpResult with response or err.

        """
        headers = kwargs.pop("headers", None) or {}
        headers["User-Agent"] = self.user_agent
        kwargs["headers"] = headers

        return self._execute(
            "POST",
            url,
            lambda u, **kw: requests.post(u, data=data, json=json, **kw),
            lambda u, exc, kw: self._post_ssl_fallback(u, data, json, exc, kw),
            max(1, retries),
            **kwargs,
        )

    def _post_ssl_fallback(
        self,
        url: str,
        data: Any,
        json: Any,
        primary_exc: requests.exceptions.SSLError,
        kwargs: dict[str, Any],
    ) -> HttpResult:
        """SSL fallback for POST — strips 'verify' from kwargs."""
        fallback_kwargs = {k: v for k, v in kwargs.items() if k != "verify"}
        try:
            response = self._session.post(
                url,
                data=data,
                json=json,
                timeout=self.timeout,
                verify=False,
                **fallback_kwargs,
            )
            return HttpResult(response=response, err=None, ssl_fallback_used=True)
        except requests.exceptions.RequestException as fallback_exc:
            logger.warning(
                "Fallback POST also failed for %s: %s", url, fallback_exc
            )
            return HttpResult(
                response=None,
                err=HttpFallbackError(
                    primary_error=primary_exc, fallback_error=fallback_exc
                ),
                ssl_fallback_used=False,
            )
        except Exception as exc:
            return HttpResult(response=None, err=exc, ssl_fallback_used=False)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_retry_after(response: requests.Response) -> float | None:
        """Parse Retry-After header, return seconds to wait or None.

        Supports both integer seconds (Retry-After: 120) and
        HTTP-date format (Retry-After: Wed, 21 Oct 2026 07:28:00 GMT).
        """
        retry_after = response.headers.get("Retry-After")
        if retry_after is None:
            return None
        # Try integer seconds first
        try:
            return float(retry_after)
        except ValueError:
            pass
        # Try HTTP-date format
        try:
            parsed = parsedate_to_datetime(retry_after)
            now = datetime.datetime.now(datetime.timezone.utc)
            delta = (parsed - now).total_seconds()
            return max(0.0, delta)
        except Exception:
            return None
