"""Tests per location_urls/expand_glob — location registry → URL leggibili."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lab_connectors.gcs.paths import expand_glob, location_urls

pytestmark = pytest.mark.contract


class TestLocationUrls:
    def test_path_singolo_stringa(self) -> None:
        assert location_urls("gs://bucket/prefix/s/2024/s_2024_clean.parquet") == [
            "https://storage.googleapis.com/bucket/prefix/s/2024/s_2024_clean.parquet"
        ]

    def test_dict_con_glob_e_anni(self) -> None:
        loc = {"path": "gs://bucket/p/s/*/s_*_clean.parquet", "multi_file": True}
        assert location_urls(loc, years=[2024, 2025]) == [
            "https://storage.googleapis.com/bucket/p/s/2024/s_2024_clean.parquet",
            "https://storage.googleapis.com/bucket/p/s/2025/s_2025_clean.parquet",
        ]

    def test_oggetto_location_registry(self) -> None:
        loc = SimpleNamespace(path="gs://bucket/p/s/2024/s_2024_clean.parquet")
        assert location_urls(loc) == [
            "https://storage.googleapis.com/bucket/p/s/2024/s_2024_clean.parquet"
        ]

    def test_path_non_gcs(self) -> None:
        assert location_urls({"path": "out/data/clean/s/2024/x.parquet"}) == []
        assert location_urls("") == []

    def test_glob_senza_anni_espande_il_bucket(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "lab_connectors.gcs.client.list_objects",
            lambda *_a, **_k: [
                {"name": "p/s/2024/s_2024_clean.parquet"},
                {"name": "p/s/2025/s_2025_clean.parquet"},
                {"name": "p/s/2025/altro.json"},
            ],
        )
        assert location_urls({"path": "gs://bucket/p/s/*/s_*_clean.parquet"}) == [
            "https://storage.googleapis.com/bucket/p/s/2024/s_2024_clean.parquet",
            "https://storage.googleapis.com/bucket/p/s/2025/s_2025_clean.parquet",
        ]


class TestExpandGlob:
    def test_senza_wildcard_invariato(self) -> None:
        assert expand_glob("gs://bucket/x.parquet") == ["gs://bucket/x.parquet"]

    def test_schema_non_valido(self) -> None:
        with pytest.raises(ValueError):
            expand_glob("https://example.com/*.parquet")

    def test_listing_fallito_propaga(self, monkeypatch) -> None:
        def boom(*_a, **_k):
            raise RuntimeError("rete")

        monkeypatch.setattr("lab_connectors.gcs.client.list_objects", boom)
        with pytest.raises(RuntimeError, match="rete"):
            expand_glob("gs://bucket/p/*/x.parquet")
