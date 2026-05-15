"""HTTP client with SSL fallback and retry for DataCivicLab.

This module provides a shared HTTP client used by all Lab repos.
It wraps requests with:
- SSL fallback (verify=False on SSLError)
- Configurable timeout
- User-Agent
- HEAD, GET and POST methods
- HttpResult return type (no exceptions raised on HTTP errors)
"""
from __future__ import annotations

import logging
from typing import Any

import requests
import urllib3
from urllib3.exceptions import InsecureRequestWarning

from lab_connectors.http.types import HttpFallbackError, HttpResult

logger = logging.getLogger("lab_connectors.http")


class HttpClient:
    """HTTP client with SSL fallback and retry.

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
        user_agent: str | None = None,
    ):
        """Initialize HttpClient.

        Args:
            timeout: Request timeout in seconds.
            max_retries: Number of retries on transient errors.
            user_agent: Custom User-Agent string.

        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT

    def head(self, url: str, **kwargs: Any) -> HttpResult:
        """Send HEAD request with SSL fallback.

        Args:
            url: The URL to request.
            **kwargs: Passed to requests.head().

        Returns:
            HttpResult with response or err. On SSL fallback success,
            ssl_fallback_used=True.

        """
        headers = kwargs.pop("headers", None) or {}
        headers["User-Agent"] = self.user_agent
        kwargs["headers"] = headers
        kwargs.setdefault("allow_redirects", True)
        kwargs_no_headers = {k: v for k, v in kwargs.items() if k != "headers"}

        primary_exc: requests.exceptions.SSLError | None = None
        try:
            response = requests.head(url, timeout=self.timeout, **kwargs)
            return HttpResult(response=response, err=None, ssl_fallback_used=None)
        except requests.exceptions.SSLError as exc:
            primary_exc = exc
            logger.warning("SSL error on HEAD %s — fallback with verify=False", url)
            urllib3.disable_warnings(category=InsecureRequestWarning)

        # Fallback attempt with verify=False — preserve all original kwargs
        try:
            with requests.Session() as session:
                session.headers.update({"User-Agent": self.user_agent})
                response = session.head(
                    url,
                    timeout=self.timeout,
                    allow_redirects=True,
                    verify=False,
                    **kwargs_no_headers,
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

    def get(self, url: str, **kwargs: Any) -> HttpResult:
        """Send GET request with SSL fallback and retry.

        Args:
            url: The URL to request.
            **kwargs: Passed to requests.get().

        Returns:
            HttpResult with response or err. On SSL fallback success,
            ssl_fallback_used=True.

        """
        headers = kwargs.pop("headers", None) or {}
        headers["User-Agent"] = self.user_agent
        kwargs["headers"] = headers

        last_err: Exception | None = None
        primary_exc: requests.exceptions.SSLError | None = None

        for attempt in range(max(1, self.max_retries)):
            try:
                response = requests.get(url, timeout=self.timeout, **kwargs)
                if response.status_code >= 500 and attempt < self.max_retries - 1:
                    last_err = Exception(f"HTTP {response.status_code}")
                    continue
                return HttpResult(response=response, err=None, ssl_fallback_used=None)
            except requests.exceptions.SSLError as exc:
                primary_exc = exc
                logger.warning("SSL error on GET %s (attempt %d) — fallback", url, attempt + 1)
                urllib3.disable_warnings(category=InsecureRequestWarning)

                # SSL fallback attempt
                try:
                    with requests.Session() as session:
                        session.headers.update({"User-Agent": self.user_agent})
                        response = session.get(url, timeout=self.timeout, verify=False, **kwargs)
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

            except requests.exceptions.RequestException as exc:
                last_err = exc
                if attempt < self.max_retries - 1:
                    continue
                return HttpResult(response=None, err=exc, ssl_fallback_used=False)
            except Exception as exc:
                return HttpResult(response=None, err=exc, ssl_fallback_used=False)

        return HttpResult(
            response=None,
            err=last_err or Exception("Max retries exhausted"),
            ssl_fallback_used=False,
        )

    def post(
        self,
        url: str,
        data: Any = None,
        json: Any = None,
        **kwargs: Any,
    ) -> HttpResult:
        """Send POST request with SSL fallback and retry.

        Follows the same retry and SSL fallback pattern as :meth:`get`.

        .. caution::
           Retry on POST is safe only for **idempotent** endpoints
           (download, query, search). For state-mutating endpoints,
           pass ``max_retries=0`` to the client constructor.

        Args:
            url: The URL to request.
            data: Form-encoded body (passed as ``data`` to ``requests.post``).
            json: JSON-serializable body (passed as ``json`` to ``requests.post``).
            **kwargs: Passed to ``requests.post()``.

        Returns:
            HttpResult with response or err. On SSL fallback success,
            ssl_fallback_used=True.

        """
        headers = kwargs.pop("headers", None) or {}
        headers["User-Agent"] = self.user_agent
        kwargs["headers"] = headers

        last_err: Exception | None = None
        primary_exc: requests.exceptions.SSLError | None = None

        for attempt in range(max(1, self.max_retries)):
            try:
                response = requests.post(
                    url, data=data, json=json, timeout=self.timeout, **kwargs
                )
                if response.status_code >= 500 and attempt < self.max_retries - 1:
                    last_err = Exception(f"HTTP {response.status_code}")
                    continue
                return HttpResult(response=response, err=None, ssl_fallback_used=None)
            except requests.exceptions.SSLError as exc:
                primary_exc = exc
                logger.warning(
                    "SSL error on POST %s (attempt %d) — fallback", url, attempt + 1
                )
                urllib3.disable_warnings(category=InsecureRequestWarning)

                # SSL fallback attempt
                try:
                    with requests.Session() as session:
                        session.headers.update({"User-Agent": self.user_agent})
                        response = session.post(
                            url,
                            data=data,
                            json=json,
                            timeout=self.timeout,
                            verify=False,
                            **kwargs,
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

            except requests.exceptions.RequestException as exc:
                last_err = exc
                if attempt < self.max_retries - 1:
                    continue
                return HttpResult(response=None, err=exc, ssl_fallback_used=False)
            except Exception as exc:
                return HttpResult(response=None, err=exc, ssl_fallback_used=False)

        return HttpResult(
            response=None,
            err=last_err or Exception("Max retries exhausted"),
            ssl_fallback_used=False,
        )
