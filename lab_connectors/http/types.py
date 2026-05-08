"""Shared HTTP client types for DataCivicLab."""
from __future__ import annotations

from dataclasses import dataclass


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

    response: object | None
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