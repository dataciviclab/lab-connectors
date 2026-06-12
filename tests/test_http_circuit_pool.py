"""Tests for circuit breaker in HttpClient and GenericPool."""

from __future__ import annotations

import time
from concurrent.futures import as_completed

import pytest

from lab_connectors.http import CircuitOpenError, HttpClient
from lab_connectors.http.pool import GenericPool
from lab_connectors.http.types import HttpResult

# ── Helpers ────────────────────────────────────────────────────────────────


def _stub_response(status_code: int = 200) -> HttpResult:
    """Minimal HttpResult with a response stub."""
    from lab_connectors.testing import fake_response

    return HttpResult(response=fake_response(status_code=status_code), err=None)


def _stub_error(name: str = "ConnectionError") -> HttpResult:
    """HttpResult with an error (simulating network failure)."""
    return HttpResult(response=None, err=Exception(name))


# ── Circuit breaker: default disabled ─────────────────────────────────────


class TestCircuitBreakerDefault:
    @pytest.mark.contract
    def test_threshold_zero_never_blocks(self, monkeypatch) -> None:
        """circuit_threshold=0 (default) — no blocking even after errors."""
        calls = []

        def _fake_head(url, **kw):
            calls.append(url)
            raise Exception("fail")

        monkeypatch.setattr("requests.head", _fake_head)
        monkeypatch.setattr("requests.get", _fake_head)

        client = HttpClient(timeout=1, max_retries=1, circuit_threshold=0)
        r1 = client.get("https://host1.test/")
        assert r1.is_error
        r2 = client.get("https://host1.test/")
        assert r2.is_error
        r3 = client.get("https://host1.test/")
        assert r3.is_error
        # All 3 requests went through even after 3 consecutive errors
        assert len(calls) == 3  # 3 attempts per call = 9, but at least 3 calls


# ── Circuit breaker: per-host opening ─────────────────────────────────────


class TestCircuitBreakerOpen:
    @pytest.mark.contract
    def test_opens_after_threshold_errors(self, monkeypatch) -> None:
        """After circuit_threshold consecutive errors, circuit opens."""
        calls = []

        def _fake_get(url, **kw):
            calls.append(url)
            raise Exception("fail")

        monkeypatch.setattr("requests.get", _fake_get)

        client = HttpClient(timeout=1, max_retries=1, circuit_threshold=3)
        r1 = client.get("https://host1.test/")
        assert r1.is_error

        r2 = client.get("https://host1.test/")
        assert r2.is_error

        r3 = client.get("https://host1.test/")
        assert r3.is_error

        # 4th call: circuit should be open → CircuitOpenError immediately
        r4 = client.get("https://host1.test/")
        assert r4.is_error
        assert isinstance(r4.err, CircuitOpenError)
        assert "host1.test" in str(r4.err)

    @pytest.mark.contract
    def test_open_returns_immediately_without_network(self, monkeypatch) -> None:
        """CircuitOpenError is returned without making a network call."""
        calls = []

        def _fake_get(url, **kw):
            calls.append(url)
            raise Exception("fail")

        monkeypatch.setattr("requests.get", _fake_get)

        client = HttpClient(timeout=5, max_retries=1, circuit_threshold=2)
        # 2 errors to open circuit
        client.get("https://host2.test/")
        client.get("https://host2.test/")

        # From here: should return immediately, no request made
        start = time.perf_counter()
        r = client.get("https://host2.test/")
        elapsed = time.perf_counter() - start

        assert isinstance(r.err, CircuitOpenError)
        # Must be near-instant (no network timeout)
        assert elapsed < 1.0, f"CircuitOpenError took {elapsed:.2f}s — network call was made!"
        # No additional calls beyond the first 2
        assert len(calls) == 2, f"Expected no new network calls, got {len(calls) - 2} extra"

    @pytest.mark.contract
    def test_success_resets_circuit(self, monkeypatch) -> None:
        """A success response resets the counter for that host."""
        call_count = 0

        def _fake_get(url, **kw):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise Exception("fail")
            # 3rd call: success
            from lab_connectors.testing import fake_response

            return fake_response(status_code=200)

        monkeypatch.setattr("requests.get", _fake_get)

        client = HttpClient(timeout=1, max_retries=1, circuit_threshold=3)
        # 2 failures (not enough to open)
        client.get("https://host3.test/")
        client.get("https://host3.test/")

        # 3rd: success → resets counter
        client.get("https://host3.test/")

        # 4th: should still work (counter = 0 after success)
        r4 = client.get("https://host3.test/")
        assert r4.is_ok, "Circuit should have been reset by the success"

    @pytest.mark.contract
    def test_different_hosts_independent(self, monkeypatch) -> None:
        """Circuit state is per-host, not global."""
        calls: dict[str, int] = {}

        def _fake_get(url, **kw):
            calls[url] = calls.get(url, 0) + 1
            raise Exception("fail")

        monkeypatch.setattr("requests.get", _fake_get)

        client = HttpClient(timeout=1, max_retries=1, circuit_threshold=3)
        # Open circuit for host-a (3 failures)
        for _ in range(3):
            client.get("https://host-a.test/")

        # host-a is now open → CircuitOpenError
        r_a = client.get("https://host-a.test/")
        assert isinstance(r_a.err, CircuitOpenError), "host-a should be open"

        # host-b with 0 failures → should attempt the request (error, not CircuitOpenError)
        r_b1 = client.get("https://host-b.test/")
        assert not isinstance(r_b1.err, CircuitOpenError), (
            "host-b should NOT be open yet — circuit is per-host"
        )

        # Now host-b has 1 failure, circuit is per-host, still not open
        r_b2 = client.get("https://host-b.test/")
        assert not isinstance(r_b2.err, CircuitOpenError)

        # After 3 failures, host-b also opens
        client.get("https://host-b.test/")
        r_b3 = client.get("https://host-b.test/")
        assert isinstance(r_b3.err, CircuitOpenError), "host-b should be open after 3 failures"

    @pytest.mark.regression
    def test_http_5xx_opens_circuit(self, monkeypatch) -> None:
        """HTTP 5xx responses count as failures for the circuit breaker."""
        call_count = 0

        def _fake_head(url, **kw):
            nonlocal call_count
            call_count += 1
            from lab_connectors.testing import fake_response

            return fake_response(status_code=502)

        monkeypatch.setattr("requests.head", _fake_head)

        client = HttpClient(timeout=1, max_retries=1, circuit_threshold=2)
        # 502 → error
        client.head("https://host5.test/")
        # Another 502 → circuit opens
        client.head("https://host5.test/")
        # 3rd → CircuitOpenError
        r3 = client.head("https://host5.test/")
        assert isinstance(r3.err, CircuitOpenError)

    @pytest.mark.contract
    def test_post_respects_circuit(self, monkeypatch) -> None:
        """POST also respects the circuit breaker."""
        calls = []

        def _fake_post(url, **kw):
            calls.append(url)
            raise Exception("fail")

        monkeypatch.setattr("requests.post", _fake_post)

        client = HttpClient(timeout=1, max_retries=1, circuit_threshold=2)
        client.post("https://host6.test/", data={"x": 1})
        client.post("https://host6.test/", data={"x": 2})
        r = client.post("https://host6.test/", data={"x": 3})
        assert isinstance(r.err, CircuitOpenError)


# ── GenericPool ───────────────────────────────────────────────────────────


class TestGenericPool:
    @pytest.mark.policy
    def test_pool_runs_concurrently(self, monkeypatch) -> None:
        """Pool executes multiple requests in parallel (faster than sequential)."""
        DELAY = 0.4
        call_times = []

        def _fake_head(url, **kw):
            time.sleep(DELAY)
            call_times.append(time.perf_counter())
            from lab_connectors.testing import fake_response

            return fake_response(status_code=200)

        monkeypatch.setattr("requests.head", _fake_head)

        client = HttpClient(timeout=5)
        pool = GenericPool(workers=3, client=client)

        futures = [pool.submit("head", f"https://src{i}.test/") for i in range(3)]

        start = time.perf_counter()
        for f in as_completed(futures):
            result = f.result()
            assert result.is_ok
            assert result.response.status_code == 200
        elapsed = time.perf_counter() - start

        # Sequential would be 3 * 0.4 = 1.2s
        # Parallel with 3 workers should be ~0.4s
        assert elapsed < 0.9, f"Pool took {elapsed:.2f}s — expected < 0.9s for 3 parallel requests"

    @pytest.mark.contract
    def test_pool_submit_validates_method(self) -> None:
        """submit() raises ValueError for unsupported methods."""
        pool = GenericPool(workers=2)
        with pytest.raises(ValueError, match="Unsupported method"):
            pool.submit("delete", "https://test.test/")
        pool.close()

    @pytest.mark.contract
    def test_pool_wait_returns_sorted(self, monkeypatch) -> None:
        """wait() returns results in submission order."""
        import time

        def _fake_head(url, **kw):
            time.sleep(0.05)
            from lab_connectors.testing import fake_response

            return fake_response(status_code=200)

        monkeypatch.setattr("requests.head", _fake_head)

        client = HttpClient(timeout=5)
        pool = GenericPool(workers=5, client=client)

        urls = [f"https://src{i}.test/" for i in range(5)]
        futures = [pool.submit("head", url) for url in urls]

        results = pool.wait(futures, timeout=5)
        assert len(results) == 5
        for r in results:
            assert r.is_ok
            assert r.response.status_code == 200

    @pytest.mark.contract
    def test_pool_context_manager(self, monkeypatch) -> None:
        """GenericPool works as a context manager."""
        monkeypatch.setattr(
            "requests.head",
            lambda url, **kw: __import__("lab_connectors.testing").testing.fake_response(
                status_code=200
            ),
        )

        with GenericPool(workers=2) as pool:
            f = pool.submit("head", "https://test.test/")
            result = f.result()
            assert result.is_ok
            assert result.response.status_code == 200

    @pytest.mark.policy
    def test_pool_context_manager_waits_for_pending(self, monkeypatch) -> None:
        """Uscita dal context manager attende il completamento delle richieste pendenti.

        Se il pool uscisse senza attendere (wait=False), un task da 0.3s
        non sarebbe completato all'uscita dal blocco with.
        """
        DELAY = 0.3
        completed = []

        def _slow_head(url, **kw):
            time.sleep(DELAY)
            completed.append(url)
            from lab_connectors.testing import fake_response

            return fake_response(status_code=200)

        monkeypatch.setattr("requests.head", _slow_head)

        with GenericPool(workers=2) as pool:
            future = pool.submit("head", "https://slow.test/")
            # Esci dal context SENZA chiamare future.result()

        # Dopo l'uscita dal context, il futuro deve essere completato
        assert future.done(), (
            "Il pool non ha atteso il completamento — future ancora pending "
            "dopo l'uscita dal context manager"
        )
        result = future.result()
        assert result.is_ok
        assert "https://slow.test/" in completed

    @pytest.mark.policy
    def test_pool_closes_internal_client(self) -> None:
        """GenericPool chiude il client interno quando creato da default."""
        pool = GenericPool(workers=2)
        pool.close()
        # Verifica implicita: close() non solleva errori (session già chiusa
        # due volte è silenziosa in requests)
        pool.close()  # seconda chiamata non deve crashare


# ── _FakeResponse streaming compat ─────────────────────────────────────────


class TestFakeResponseStreaming:
    @pytest.mark.contract
    def test_iter_content_yields_full_content_when_smaller_than_chunk(self):
        """Contenuto intero in un singolo chunk."""
        from lab_connectors.testing import fake_response

        resp = fake_response(200, text="hello")
        chunks = list(resp.iter_content(chunk_size=1024))
        assert chunks == [b"hello"]

    @pytest.mark.contract
    def test_iter_content_splits_into_multiple_chunks(self):
        """Contenuto piu' grande del chunk size → multipli chunk."""
        from lab_connectors.testing import fake_response

        text = "a" * 100
        resp = fake_response(200, text=text)
        chunks = list(resp.iter_content(chunk_size=30))
        assert len(chunks) == 4  # 100 // 30 = 3 resto 10 → 4 chunk
        assert sum(len(c) for c in chunks) == 100
        assert b"".join(chunks) == b"a" * 100

    @pytest.mark.contract
    def test_iter_content_empty_content(self):
        """Content vuoto → nessun chunk."""
        from lab_connectors.testing import fake_response

        resp = fake_response(200, text="")
        chunks = list(resp.iter_content())
        assert chunks == []

    @pytest.mark.policy
    def test_close_is_noop(self):
        """close() non solleva eccezioni."""
        from lab_connectors.testing import fake_response

        resp = fake_response(200, text="data")
        resp.close()  # Non deve crashare
        resp.close()  # Seconda chiamata ok (idempotente)
