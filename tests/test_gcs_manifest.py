"""Test per lab_connectors.gcs.manifest."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from lab_connectors.gcs.manifest import build_manifest, read_manifest


def _fake_urlopen(data: bytes) -> MagicMock:
    """Crea un mock di urlopen che funge da context manager."""
    resp = MagicMock()
    resp.read.return_value = data
    cm = MagicMock()
    cm.__enter__.return_value = resp
    return cm


class TestBuildManifest:
    """build_manifest() — aggregazione oggetti da list_objects."""

    @pytest.mark.pure_unit
    def test_build_manifest_success(self):
        """Scansione di bucket con file misti."""
        fake_objects_a = [
            {"name": "aifa_spesa/2024/file_clean.parquet", "size": 2048, "updated": "2026-06-01"},
            {"name": "aifa_spesa/2023/file_clean.parquet", "size": 1024, "updated": "2026-05-01"},
            {"name": "aifa_spesa/2024/pipeline_run.json", "size": 512, "updated": "2026-06-01"},
        ]
        # build_manifest scansiona 2 bucket: secondo vuoto
        with patch("lab_connectors.gcs.manifest.list_objects", side_effect=[fake_objects_a, []]):
            manifest = build_manifest()

        assert manifest["file_count"] == 3
        assert manifest["total_size_bytes"] == 2048 + 1024 + 512
        assert len(manifest["files"]) == 3
        assert manifest["files"][0]["slug"] == "aifa_spesa"
        assert manifest["files"][0]["year"] == 2024
        assert manifest["files"][0]["bucket"] == "dataciviclab-clean"
        assert manifest["files"][0]["url"].startswith("s3://")
        assert "generated_at" in manifest
        assert "buckets" in manifest

    @pytest.mark.pure_unit
    def test_build_manifest_file_no_year(self):
        """File senza anno nel path non rompe."""
        fake_objects_a = [
            {"name": "radar/radar_summary.json", "size": 512, "updated": "2026-06-01"},
        ]
        with patch("lab_connectors.gcs.manifest.list_objects", side_effect=[fake_objects_a, []]):
            manifest = build_manifest()

        assert manifest["file_count"] == 1
        assert manifest["files"][0]["slug"] == "radar"
        assert manifest["files"][0]["year"] is None

    @pytest.mark.pure_unit
    def test_build_manifest_empty(self):
        """Bucket vuoto."""
        with patch("lab_connectors.gcs.manifest.list_objects", return_value=[]):
            manifest = build_manifest()

        # 2 bucket, entrambi vuoti → 0 file
        assert manifest["file_count"] == 0
        assert manifest["files"] == []


class TestReadManifest:
    """read_manifest() — fetch e parsing del manifest pubblico."""

    @pytest.mark.pure_unit
    def test_read_manifest_success(self):
        """JSON valido restituisce dict."""
        fake_data = {"generated_at": "2026-06-21", "file_count": 10, "files": []}
        fake_urlopen = _fake_urlopen(json.dumps(fake_data).encode("utf-8"))

        with patch("urllib.request.urlopen", return_value=fake_urlopen):
            result = read_manifest("https://example.com/manifest.json")

        assert result["file_count"] == 10

    @pytest.mark.contract
    def test_read_manifest_404(self):
        """404 solleva FileNotFoundError."""
        from urllib.error import HTTPError

        fake_error = HTTPError("https://example.com/404", 404, "Not Found", {}, None)

        with patch("urllib.request.urlopen", side_effect=fake_error):
            with pytest.raises(FileNotFoundError):
                read_manifest("https://example.com/404")

    @pytest.mark.contract
    def test_read_manifest_403(self):
        """403 solleva FileNotFoundError."""
        from urllib.error import HTTPError

        fake_error = HTTPError("https://example.com/403", 403, "Forbidden", {}, None)

        with patch("urllib.request.urlopen", side_effect=fake_error):
            with pytest.raises(FileNotFoundError):
                read_manifest("https://example.com/403")

    @pytest.mark.contract
    def test_read_manifest_500(self):
        """500 solleva RuntimeError."""
        from urllib.error import HTTPError

        fake_error = HTTPError("https://example.com/500", 500, "Server Error", {}, None)

        with patch("urllib.request.urlopen", side_effect=fake_error):
            with pytest.raises(RuntimeError):
                read_manifest("https://example.com/500")

    @pytest.mark.contract
    def test_read_manifest_corrupted_json(self):
        """JSON malformato solleva ValueError."""
        fake_urlopen = _fake_urlopen(b"not json at all")

        with patch("urllib.request.urlopen", return_value=fake_urlopen):
            with pytest.raises(ValueError, match="corrotto"):
                read_manifest("https://example.com/corrupted")

    @pytest.mark.contract
    def test_read_manifest_timeout(self):
        """Timeout solleva TimeoutError."""
        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            with pytest.raises(TimeoutError):
                read_manifest("https://example.com/timeout")
