"""Cache generica thread-safe con TTL per MCP server.

Usata internamente da ArtifactResolver e a disposizione dei server MCP
per cache specializzate (es. list GCS, schemi parquet).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


@dataclass
class CacheStats:
    """Statistiche della cache."""

    entries: int
    """Numero di chiavi in cache."""
    oldest_age_seconds: float
    """Età della entry più vecchia (secondi)."""
    ttl_seconds: int
    """TTL configurato."""


class TtlCache(Generic[K, V]):
    """Cache generica thread-safe con expiration basata su TTL.

    Tipi::

        cache: TtlCache[str, list[str]] = TtlCache(ttl_seconds=300)
        cache.set("slug-2024", ["gs://.../file1.parquet"])
        urls = cache.get("slug-2024")

    Args:
        ttl_seconds: Durata di validità delle entry (default 300 = 5 min).

    """

    def __init__(self, ttl_seconds: int = 300) -> None:
        """Inizializza la cache con TTL configurabile."""
        self._ttl = ttl_seconds
        self._data: dict[K, tuple[float, V]] = {}
        self._lock = threading.Lock()

    def get(self, key: K) -> V | None:
        """Restituisce il valore se presente e non scaduto, altrimenti None."""
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            ts, value = entry
            if time.monotonic() - ts > self._ttl:
                del self._data[key]
                return None
            return value

    def set(self, key: K, value: V) -> None:
        """Inserisce o sovrascrive una entry."""
        with self._lock:
            self._data[key] = (time.monotonic(), value)

    def invalidate(self, key: K) -> None:
        """Rimuove una specifica chiave."""
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        """Svuota l'intera cache."""
        with self._lock:
            self._data.clear()

    @property
    def stats(self) -> CacheStats:
        """Statistiche correnti della cache."""
        with self._lock:
            now = time.monotonic()
            ages = [now - ts for ts, _ in self._data.values()]
            oldest = max(ages) if ages else 0.0
            return CacheStats(
                entries=len(self._data),
                oldest_age_seconds=oldest,
                ttl_seconds=self._ttl,
            )
