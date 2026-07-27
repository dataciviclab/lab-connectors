"""Generic HTTP thread pool for parallel requests.

Provides ``GenericPool`` — a thread pool wrapper around ``HttpClient``
that runs multiple HTTP requests concurrently.  Pool members share
a single ``HttpClient`` instance (with its connection pool and optional
circuit breaker).

Usage::

    from lab_connectors.http import HttpClient
    from lab_connectors.http.pool import GenericPool

    pool = GenericPool(workers=8, client=HttpClient(circuit_threshold=3))
    futures = {}
    for url in urls:
        futures[pool.submit("head", url)] = url

    for future in as_completed(futures):
        url = futures[future]
        result = future.result()
        print(url, result.is_ok)
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Any

from lab_connectors.http.client import HttpClient
from lab_connectors.http.types import HttpResult

_METHODS = frozenset({"head", "get", "post"})


class GenericPool:
    """Thread pool for parallel HTTP requests.

    Wraps a ``ThreadPoolExecutor`` and an ``HttpClient``.  Each worker
    thread calls the specified method on the shared client.

    Args:
        workers: Max worker threads (default 10).
        client: ``HttpClient`` instance to use.  A new default client
            is created if omitted.

    """

    def __init__(
        self,
        workers: int = 10,
        client: HttpClient | None = None,
    ) -> None:
        """Initialize the pool with the given number of worker threads.

        If *client* is not provided, a new ``HttpClient`` is created
        internally and closed when the pool is closed.
        """
        self._pool = ThreadPoolExecutor(max_workers=workers)
        self._owns_client = client is None
        self._client = client or HttpClient()

    def submit(self, method: str, url: str, **kwargs: Any) -> Future:
        """Submit a single HTTP request to the pool.

        Args:
            method: HTTP method name — ``"head"``, ``"get"``, or ``"post"``.
            url: The URL to request.
            **kwargs: Forwarded to the underlying ``HttpClient`` method.

        Returns:
            A ``concurrent.futures.Future`` whose ``.result()`` returns
            an ``HttpResult``.

        Raises:
            ValueError: If *method* is not one of the supported methods.

        """
        if method not in _METHODS:
            raise ValueError(f"Unsupported method {method!r}. Supported: {sorted(_METHODS)}")
        fn = getattr(self._client, method)
        return self._pool.submit(fn, url, **kwargs)

    @staticmethod
    def wait(futures: list[Future], timeout: float | None = None) -> list[HttpResult]:
        """Wait for all futures and return results in submission order.

        Args:
            futures: List of futures returned by ``submit()``.
            timeout: Max seconds to wait in total.  ``None`` = no limit.

        Returns:
            List of ``HttpResult`` in the same order as *futures*.

        Raises:
            TimeoutError: If the timeout expires before all futures complete.

        """
        done = set()
        for f in as_completed(futures, timeout=timeout):
            done.add(f)
        return [f.result() for f in futures]

    def close(self) -> None:
        """Shut down the thread pool, waiting for pending futures to complete.

        If the pool owns the internal ``HttpClient`` (created via default),
        its session is also closed.
        """
        self._pool.shutdown(wait=True)
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> GenericPool:
        """Enter context manager — returns self."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit context manager — calls close()."""
        self.close()
