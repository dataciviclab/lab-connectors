"""Shared HTTP client types for DataCivicLab."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class HttpFallbackError(Exception):
    """Raised when both primary SSL attempt and fallback (verify=False) fail.

    Preserves both errors for diagnostic purposes.
    """

    primary_error: Exception
    fallback_error: Exception

    def __str__(self) -> str:
        return (
            f"primary failed with {self.primary_error.__class__.__name__}; "
            f"fallback failed with {self.fallback_error.__class__.__name__}"
        )


class CircuitOpenError(Exception):
    """Request skipped because the circuit breaker is open for that host.

    The circuit is per-host: after ``circuit_threshold`` consecutive errors
    (timeout, connection error, HTTP 5xx) on the same host, subsequent
    requests to that host return this error immediately without making a
    network call.
    """


@dataclass
class HttpResult:
    """Result of an HTTP request.

    Attributes:
        response: the HTTP response if the request succeeded, None otherwise.
        err: Exception if the request failed, None otherwise.
        ssl_fallback_used: True if the primary SSL attempt failed but fallback
                          (verify=False) succeeded. None if no fallback was needed.
                          False if both primary and fallback failed.

    """

    response: Any  # requests.Response in produzione, test stub in test
    err: Exception | None
    ssl_fallback_used: bool | None = None

    def as_tuple(self) -> tuple[object | None, Exception | None]:
        """Explicit tuple conversion for callers that need tuple unpacking."""
        return (self.response, self.err)

    @property
    def is_ok(self) -> bool:
        """True if response is usable (err is None)."""
        return self.response is not None and self.err is None

    @property
    def is_error(self) -> bool:
        """True if request completely failed."""
        return self.response is None and self.err is not None

    @property
    def is_ssl_fallback_failed(self) -> bool:
        """True if both primary SSL and fallback failed."""
        return (
            self.err is not None
            and self.ssl_fallback_used is False
            and isinstance(self.err, HttpFallbackError)
        )
