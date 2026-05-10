"""Tests per lab_connectors.mcp.cache."""
from __future__ import annotations

import time

from lab_connectors.mcp.cache import TtlCache


class TestTtlCache:
    def test_get_set(self) -> None:
        cache: TtlCache[str, str] = TtlCache(ttl_seconds=60)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_missing(self) -> None:
        cache: TtlCache[str, str] = TtlCache(ttl_seconds=60)
        assert cache.get("nonexistent") is None

    def test_expiration(self) -> None:
        cache: TtlCache[str, str] = TtlCache(ttl_seconds=0.01)
        cache.set("key1", "value1")
        time.sleep(0.02)
        assert cache.get("key1") is None

    def test_overwrite(self) -> None:
        cache: TtlCache[str, str] = TtlCache(ttl_seconds=60)
        cache.set("key1", "value1")
        cache.set("key1", "value2")
        assert cache.get("key1") == "value2"

    def test_invalidate(self) -> None:
        cache: TtlCache[str, str] = TtlCache(ttl_seconds=60)
        cache.set("key1", "value1")
        cache.invalidate("key1")
        assert cache.get("key1") is None

    def test_clear(self) -> None:
        cache: TtlCache[str, str] = TtlCache(ttl_seconds=60)
        cache.set("a", "1")
        cache.set("b", "2")
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_stats(self) -> None:
        cache: TtlCache[str, str] = TtlCache(ttl_seconds=300)
        cache.set("a", "1")
        cache.set("b", "2")
        stats = cache.stats
        assert stats.entries == 2
        assert stats.ttl_seconds == 300
        assert stats.oldest_age_seconds >= 0

    def test_stats_empty(self) -> None:
        cache: TtlCache[str, str] = TtlCache(ttl_seconds=300)
        stats = cache.stats
        assert stats.entries == 0
        assert stats.oldest_age_seconds == 0.0

    def test_thread_safety(self) -> None:
        import threading

        cache: TtlCache[int, int] = TtlCache(ttl_seconds=60)
        errors: list[Exception] = []

        def worker(n: int) -> None:
            try:
                for i in range(100):
                    cache.set(i + n * 100, i)
                    cache.get(i + n * 100)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errori di concorrenza: {errors}"
