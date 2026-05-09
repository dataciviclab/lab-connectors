"""Tests per lab_connectors.mcp.artifact."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from lab_connectors.mcp.artifact import (
    ArtifactResolver,
    _backend_from_env,
    _file_age_hours,
    _gcs_http_url,
)
from lab_connectors.mcp.errors import ErrorCode, McpError


class TestHelpers:
    def test_gcs_http_url_conversion(self) -> None:
        result = _gcs_http_url("gs://bucket/path/file.parquet")
        assert result == "https://storage.googleapis.com/bucket/path/file.parquet"

    def test_gcs_http_url_preserves_https(self) -> None:
        url = "https://storage.googleapis.com/bucket/file.parquet"
        assert _gcs_http_url(url) == url

    def test_file_age_hours_nonexistent(self) -> None:
        assert _file_age_hours(Path("/nonexistent/file.xyz")) is None

    def test_file_age_hours_existing(self) -> None:
        with tempfile.NamedTemporaryFile() as f:
            age = _file_age_hours(Path(f.name))
            assert age is not None
            assert age >= 0

    def test_backend_from_env_default(self) -> None:
        if "MCP_ARTIFACT_BACKEND" in os.environ:
            del os.environ["MCP_ARTIFACT_BACKEND"]
        assert _backend_from_env() == "auto"

    def test_backend_from_env_override(self) -> None:
        os.environ["MCP_ARTIFACT_BACKEND"] = "gcs"
        assert _backend_from_env() == "gcs"
        del os.environ["MCP_ARTIFACT_BACKEND"]

    def test_backend_from_env_invalid_fallback(self) -> None:
        os.environ["MCP_ARTIFACT_BACKEND"] = "invalid"
        assert _backend_from_env() == "auto"
        del os.environ["MCP_ARTIFACT_BACKEND"]


class TestArtifactResolverLocal:
    def setup_method(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp())
        self._repo_root = self._tmpdir / "repo"
        self._repo_root.mkdir()
        # Crea un artifact locale
        self._artifact = self._repo_root / "data" / "test.json"
        self._artifact.parent.mkdir(parents=True)
        self._artifact.write_text(json.dumps({"key": "value"}))

    def teardown_method(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir)

    def test_resolve_local_json(self) -> None:
        resolver = ArtifactResolver(
            repo_root=self._repo_root,
            backend="local",
        )
        result = resolver.resolve_json("data/test.json")
        assert result.source == "local_cache"
        assert result.path == self._artifact
        assert result.uri == str(self._artifact)

    def test_resolve_local_not_found(self) -> None:
        resolver = ArtifactResolver(
            repo_root=self._repo_root,
            backend="local",
        )
        with pytest.raises(McpError) as excinfo:
            resolver.resolve_json("data/nonexistent.json")
        assert excinfo.value.code == ErrorCode.ARTIFACT_NOT_FOUND

    def test_resolve_with_gcs_prefix_auto_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """In modalità auto, se GCS fallisce, usa locale."""
        resolver = ArtifactResolver(
            repo_root=self._repo_root,
            gcs_prefix="gs://test-bucket",
            backend="auto",
        )

        def _mock_download(*args: object, **kwargs: object) -> None:
            raise McpError(ErrorCode.GCS_UNAVAILABLE, "GCS mock failure")
        monkeypatch.setattr(resolver, "_download_gcs", _mock_download)

        result = resolver.resolve_json("data/test.json")
        assert result.source == "local_cache"
        assert result.fallback_warning is not None
        assert "GCS non disponibile" in result.fallback_warning

    def test_resolve_gcs_only_fails_hard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """In modalità gcs, se GCS fallisce, propaga errore."""
        resolver = ArtifactResolver(
            repo_root=self._repo_root,
            gcs_prefix="gs://test-bucket",
            backend="gcs",
        )

        def _mock_download(*args: object, **kwargs: object) -> None:
            raise McpError(ErrorCode.GCS_UNAVAILABLE, "GCS mock failure")
        monkeypatch.setattr(resolver, "_download_gcs", _mock_download)

        with pytest.raises(McpError) as excinfo:
            resolver.resolve_json("data/test.json")
        assert excinfo.value.code == ErrorCode.GCS_UNAVAILABLE

    def test_to_dict_includes_provenance(self) -> None:
        resolver = ArtifactResolver(
            repo_root=self._repo_root,
            backend="local",
        )
        result = resolver.resolve_json("data/test.json")
        d = result.to_dict()
        assert d["source"] == "local_cache"
        assert d["path"] == str(self._artifact)
        assert "uri" in d
        assert "age_hours" in d
        assert d["stale"] is False
