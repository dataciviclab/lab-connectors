"""Tests per source mode e fallback remote in lab_connectors.duckdb.queries."""

from __future__ import annotations

import pytest

from lab_connectors.duckdb import queries

pytestmark = pytest.mark.pure_unit


class TestResolveUrlSource:
    def test_gcs_ignora_local_root(self, tmp_path) -> None:
        url = queries._resolve_url(
            "clean",
            "clean_parquet",
            local_root=str(tmp_path),
            slug="demo",
            source="gcs",
            year=2024,
        )
        assert url.startswith("https://storage.googleapis.com/")
        assert str(tmp_path) not in url

    def test_local_restituisce_path_locale_senza_prefix(self, tmp_path) -> None:
        url = queries._resolve_url(
            "clean",
            "clean_parquet",
            prefix="repo/",
            local_root=str(tmp_path),
            slug="demo",
            source="local",
            year=2024,
        )
        assert url == f"{tmp_path}/clean/demo/2024/demo_2024_clean.parquet"

    def test_local_senza_out_data_fallisce(self, monkeypatch) -> None:
        monkeypatch.setattr(queries, "_detect_local_root", lambda repo_root=None: None)
        with pytest.raises(FileNotFoundError, match="out/data"):
            queries._resolve_url("clean", "clean_parquet", slug="demo", source="local", year=2024)

    def test_source_non_valido(self) -> None:
        with pytest.raises(ValueError, match="source"):
            queries._resolve_url("clean", "clean_parquet", slug="demo", source="raw")


class TestFallbackRemote:
    def _capture(self, monkeypatch) -> list[str]:
        seen: list[str] = []

        def fake_df(sql: str):
            seen.append(sql)
            if "storage.googleapis.com" in sql:
                return "remote"
            raise RuntimeError("IO Error: No files found that match the pattern")

        monkeypatch.setattr(queries, "_query_df", fake_df)
        return seen

    def test_riprova_su_gcs_se_il_locale_manca(self, monkeypatch, tmp_path) -> None:
        seen = self._capture(monkeypatch)
        result = queries.load_mart_table(
            "demo", "mart_x", 2024, local_root=str(tmp_path), fallback_remote=True
        )
        assert result == "remote"
        assert len(seen) == 2
        assert "storage.googleapis.com" in seen[1]

    def test_senza_fallback_l_errore_propaga(self, monkeypatch, tmp_path) -> None:
        seen = self._capture(monkeypatch)
        with pytest.raises(RuntimeError, match="No files found"):
            queries.load_mart_table(
                "demo", "mart_x", 2024, local_root=str(tmp_path), fallback_remote=False
            )
        assert len(seen) == 1

    def test_source_gcs_non_ha_fallback(self, monkeypatch, tmp_path) -> None:
        seen = self._capture(monkeypatch)
        result = queries.load_mart_table(
            "demo",
            "mart_x",
            2024,
            local_root=str(tmp_path),
            source="gcs",
            fallback_remote=True,
        )
        assert result == "remote"
        assert len(seen) == 1

    def test_query_clean_fallback(self, monkeypatch, tmp_path) -> None:
        seen = self._capture(monkeypatch)
        result = queries.query_clean(
            "demo",
            "SELECT * FROM clean_input",
            [2024],
            local_root=str(tmp_path),
            fallback_remote=True,
        )
        assert result == "remote"
        assert "clean_input" in seen[1]

    def test_errore_non_locale_propaga(self, monkeypatch) -> None:
        def fake_df(sql: str):
            raise RuntimeError("HTTP 403")

        monkeypatch.setattr(queries, "_query_df", fake_df)
        with pytest.raises(RuntimeError, match="403"):
            queries.load_mart_table("demo", "mart_x", 2024, fallback_remote=True)


def test_is_missing_local_file_error() -> None:
    assert queries.is_missing_local_file_error(
        RuntimeError("IO Error: No files found that match the pattern")
    )
    assert queries.is_missing_local_file_error(FileNotFoundError("No such file or directory"))
    assert not queries.is_missing_local_file_error(RuntimeError("HTTP 404"))
