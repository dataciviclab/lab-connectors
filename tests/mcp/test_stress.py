"""Stress test e edge case per lab_connectors.mcp.

Copre scenari di concorrenza, boundary, error propagation e carico.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path

import pytest

from lab_connectors.mcp import guard, guard_timed
from lab_connectors.mcp.artifact import ArtifactResolver
from lab_connectors.mcp.cache import TtlCache
from lab_connectors.mcp.errors import ErrorCode, McpError


# ─── TtlCache Stress Tests ──────────────────────────────────────────────────


class TestTtlCacheStress:
    def test_high_concurrency_read_write(self) -> None:
        """100 thread in competizione su 10 chiavi."""
        cache: TtlCache[int, int] = TtlCache(ttl_seconds=60)
        errors: list[Exception] = []
        lock = threading.Lock()

        def worker(tid: int) -> None:
            try:
                for i in range(200):
                    key = i % 10
                    cache.set(key, tid * 1000 + i)
                    val = cache.get(key)
                    # val può essere None se scaduto, ma TTL è 60s → non scade
                    if val is not None and not isinstance(val, int):
                        raise TypeError(f"Valore non intero: {val}")
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Errori di concorrenza ({len(errors)}): {errors[:5]}"
        stats = cache.stats
        assert stats.entries <= 10  # solo 10 chiavi uniche

    def test_expiry_exact_boundary(self) -> None:
        """Expiry a 0.001s: set e get subito dopo devono fallire."""
        cache: TtlCache[str, str] = TtlCache(ttl_seconds=0.001)
        cache.set("k", "v")
        time.sleep(0.005)
        assert cache.get("k") is None

    def test_expiry_renewal(self) -> None:
        """Re-set prima della scadenza deve estendere il TTL."""
        cache: TtlCache[str, str] = TtlCache(ttl_seconds=0.5)
        cache.set("k", "v1")
        time.sleep(0.3)  # prima di scadere
        cache.set("k", "v2")  # rinnova
        time.sleep(0.3)  # ancora prima della scadenza (vecchio TTL sarebbe scaduto)
        assert cache.get("k") == "v2"  # deve essere ancora vivo

    def test_massive_invalidate_clear(self) -> None:
        """1000 chiavi, clear, verify."""
        cache: TtlCache[int, str] = TtlCache(ttl_seconds=60)
        for i in range(1000):
            cache.set(i, f"val-{i}")
        assert cache.stats.entries == 1000
        cache.clear()
        assert cache.stats.entries == 0

    def test_invalidate_during_iteration(self) -> None:
        """Invalidate mentre altri thread leggono e scrivono."""
        cache: TtlCache[str, int] = TtlCache(ttl_seconds=60)
        stop = threading.Event()

        def writer() -> None:
            while not stop.is_set():
                for i in range(50):
                    cache.set(f"k-{i}", i)

        def invalidator() -> None:
            while not stop.is_set():
                for i in range(0, 50, 2):
                    cache.invalidate(f"k-{i}")

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=invalidator),
        ]
        for t in threads:
            t.start()
        time.sleep(1)
        stop.set()
        for t in threads:
            t.join(timeout=5)
        # Non deve crashare - verifichiamo solo che non ci siano eccezioni


# ─── ArtifactResolver Stress Tests ──────────────────────────────────────────


class TestArtifactResolverStress:
    def setup_method(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp())
        self._repo = self._tmpdir / "repo"
        self._repo.mkdir()
        (self._repo / "data").mkdir()

    def teardown_method(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir)

    def test_path_with_special_chars(self) -> None:
        """Path con spazi e caratteri speciali."""
        deep = self._repo / "data" / "my dataset" / "test (2024)"
        deep.mkdir(parents=True)
        f = deep / "file (copia).json"
        f.write_text("{}")

        resolver = ArtifactResolver(repo_root=self._repo, backend="local")
        result = resolver.resolve_json(
            "data/my dataset/test (2024)/file (copia).json"
        )
        assert result.path == f
        assert result.source == "local_cache"

    def test_relative_path_traversal(self) -> None:
        """Path con .. non deve uscire dal repo_root."""
        resolver = ArtifactResolver(repo_root=self._repo, backend="local")
        with pytest.raises(McpError) as exc:
            resolver.resolve_json("../etc/passwd")
        # Deve fallire perché ../etc/passwd non esiste nel repo
        assert exc.value.code == ErrorCode.ARTIFACT_NOT_FOUND

    def test_missing_gcs_prefix_auto(self) -> None:
        """Resolver senza gcs_prefix con backend auto deve usare locale."""
        f = self._repo / "data" / "test.json"
        f.parent.mkdir(exist_ok=True)
        f.write_text("{}")

        resolver = ArtifactResolver(
            repo_root=self._repo,
            gcs_prefix=None,  # nessun GCS
            backend="auto",
        )
        result = resolver.resolve_json("data/test.json")
        assert result.source == "local_cache"

    def test_backend_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Variabile ambiente MCP_ARTIFACT_BACKEND deve essere rispettata."""
        monkeypatch.setenv("MCP_ARTIFACT_BACKEND", "local")
        resolver = ArtifactResolver(
            repo_root=self._repo,
            gcs_prefix="gs://bucket",
            backend=None,  # deve leggere da env
        )
        assert resolver.backend == "local"

    def test_resolve_nonexistent_file_error_shape(self) -> None:
        """L'errore per file inesistente deve avere la struttura corretta."""
        resolver = ArtifactResolver(repo_root=self._repo, backend="local")
        with pytest.raises(McpError) as exc:
            resolver.resolve_json("data/nonexistent.json")
        err_dict = exc.value.to_dict()
        assert "error" in err_dict
        assert "message" in err_dict
        assert err_dict["error"] == "artifact_not_found"


# ─── Guard Stress Tests ─────────────────────────────────────────────────────


class TestGuardStress:
    def test_deep_nested_errors(self) -> None:
        """Catena di eccezioni annidate."""
        def level3() -> None:
            raise ValueError("deep error")

        def level2() -> None:
            try:
                level3()
            except ValueError as e:
                raise RuntimeError("middle") from e

        def level1() -> None:
            try:
                level2()
            except RuntimeError as e:
                raise McpError(ErrorCode.QUERY_ERROR, "top level") from e

        result = guard(level1)
        assert result["error"] == "query_error"
        assert "top level" in result["message"]

    def test_return_types_coercion(self) -> None:
        """Tipi di ritorno non-dict devono essere wrappati in {'result': ...}."""
        assert guard(lambda: "string") == {"result": "string"}
        assert guard(lambda: 42) == {"result": 42}
        assert guard(lambda: [1, 2, 3]) == {"result": [1, 2, 3]}
        assert guard(lambda: None) == {"result": None}

    def test_fn_that_modifies_args(self) -> None:
        """Funzione che modifica args mutabili."""
        def mutator(items: list[int]) -> dict:
            items.append(99)
            return {"len": len(items)}

        args = [1, 2, 3]
        result = guard(mutator, args)
        assert result == {"len": 4}
        assert args == [1, 2, 3, 99]  # effetto collaterale

    def test_mcp_error_exact_error_code(self) -> None:
        """Ogni ErrorCode deve essere mappabile via McpError."""
        for code in ErrorCode:
            err = McpError(code, f"test {code.value}")
            d = err.to_dict()
            assert d["error"] == code.value
            assert d["message"] == f"test {code.value}"

    def test_guard_timed_logging(self, caplog: pytest.LogCaptureFixture) -> None:
        """guard_timed deve loggare durata e risultato."""
        import logging
        caplog.set_level(logging.INFO)

        def quick_fn() -> dict:
            return {"ok": True}

        result = guard_timed(quick_fn, "test_tool", logger_name="stress-test")
        assert result == {"ok": True}
        assert len(caplog.records) >= 1
        log_text = caplog.text
        assert "test_tool" in log_text
        assert "OK" in log_text

    def test_guard_timed_error_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """guard_timed deve loggare warning su McpError."""
        import logging
        caplog.set_level(logging.WARNING)

        def fail_fn() -> dict:
            raise McpError(ErrorCode.INVALID_PARAMS, "bad param")

        result = guard_timed(fail_fn, "fail_tool", logger_name="stress-test")
        assert result["error"] == "invalid_params"
        # Il warning level cattura warning + error
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) >= 1


# ─── McpError Serialization ─────────────────────────────────────────────────


class TestMcpErrorShape:
    def test_to_dict_always_has_error_and_message(self) -> None:
        """Tutti gli errori devono avere 'error' e 'message'."""
        for code in ErrorCode:
            err = McpError(code, "test")
            d = err.to_dict()
            assert "error" in d
            assert "message" in d

    def test_error_code_string_representation(self) -> None:
        """ErrorCode.value deve restituire la stringa del codice."""
        assert ErrorCode.ARTIFACT_NOT_FOUND.value == "artifact_not_found"
        assert ErrorCode.GCS_UNAVAILABLE.value == "gcs_unavailable"

    def test_mcp_error_is_json_serializable(self) -> None:
        """McpError.to_dict() deve essere JSON-serializzabile."""
        err = McpError(ErrorCode.QUERY_TIMEOUT, "timeout after 60s")
        dumped = json.dumps(err.to_dict())
        loaded = json.loads(dumped)
        assert loaded == {"error": "query_timeout", "message": "timeout after 60s"}
