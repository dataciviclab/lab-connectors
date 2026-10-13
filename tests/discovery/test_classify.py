"""Tests per discovery.classify — classificazione URL e content-type.

pure_unit: is_sdmx_url, is_sparql_endpoint, resolve_preview_kind, is_file_like, is_html_content
"""

from __future__ import annotations

import pytest

from lab_connectors.discovery.classify import (
    filename_from_content_disposition,
    is_file_like,
    is_html_content,
    is_sdmx_url,
    is_sparql_endpoint,
    resolve_preview_kind,
)


class TestIsSdmxUrl:
    """pure_unit: rilevamento URL SDMX."""

    @pytest.mark.pure_unit
    def test_dataflow_path(self):
        assert is_sdmx_url("https://ex.it/dataflow/ESTAT/NAMA")

    @pytest.mark.pure_unit
    def test_sdmx_path(self):
        assert is_sdmx_url("https://ex.it/sdmx/2.1/data/NAMA")

    @pytest.mark.pure_unit
    def test_sdmx_in_url(self):
        assert is_sdmx_url("https://ex.it/sdmx-endpoint")

    @pytest.mark.pure_unit
    def test_flow_query(self):
        assert is_sdmx_url("https://ex.it/api?flow=NAMA_10R_3GDP")

    @pytest.mark.pure_unit
    def test_not_sdmx(self):
        assert not is_sdmx_url("https://ex.it/data.csv")
        assert not is_sdmx_url("https://ex.it/dataset/foo")


class TestIsSparqlEndpoint:
    """pure_unit: rilevamento endpoint SPARQL."""

    @pytest.mark.pure_unit
    def test_sparql_in_path(self):
        assert is_sparql_endpoint("https://dati.camera.it/sparql")
        assert is_sparql_endpoint("https://example.org/sparql/query")

    @pytest.mark.pure_unit
    def test_sparql_by_content_type(self):
        assert is_sparql_endpoint("https://example.org/query", "application/sparql-results+json")

    @pytest.mark.pure_unit
    def test_not_sparql(self):
        assert not is_sparql_endpoint("https://example.org/data.csv")
        assert not is_sparql_endpoint("https://example.org/data", "text/html")


class TestResolvePreviewKind:
    """pure_unit: classificazione formato preview."""

    @pytest.mark.pure_unit
    def test_from_url_extension(self):
        assert resolve_preview_kind("https://ex.it/data.csv") == "CSV"
        assert resolve_preview_kind("https://ex.it/data.json") == "JSON"
        assert resolve_preview_kind("https://ex.it/data.xlsx") == "XLSX"
        assert resolve_preview_kind("https://ex.it/data.xls") == "XLS"
        assert resolve_preview_kind("https://ex.it/data.tsv") == "TSV"

    @pytest.mark.pure_unit
    def test_from_content_disposition(self):
        result = resolve_preview_kind(
            "https://ex.it/download",
            content_disposition='attachment; filename="report.csv"',
        )
        assert result == "CSV"

    @pytest.mark.pure_unit
    def test_from_content_type(self):
        assert resolve_preview_kind("https://ex.it/api", content_type="text/csv") == "CSV"
        assert resolve_preview_kind("https://ex.it/api", content_type="application/json") == "JSON"

    @pytest.mark.pure_unit
    def test_priority_url_over_headers(self):
        """URL extension vince su headers."""
        result = resolve_preview_kind(
            "https://ex.it/data.csv",
            content_type="application/json",
        )
        assert result == "CSV"

    @pytest.mark.pure_unit
    def test_unsupported_format(self):
        assert resolve_preview_kind("https://ex.it/data.pdf") is None
        assert resolve_preview_kind("https://ex.it/page") is None


class TestIsFileLike:
    """pure_unit: classificazione file-like."""

    @pytest.mark.pure_unit
    def test_by_extension(self):
        assert is_file_like("https://ex.it/data.csv", None, None)
        assert is_file_like("https://ex.it/data.xlsx", None, None)

    @pytest.mark.pure_unit
    def test_by_content_disposition(self):
        assert is_file_like("https://ex.it/dl", None, "attachment; filename=f.csv")

    @pytest.mark.pure_unit
    def test_by_content_type(self):
        assert is_file_like("https://ex.it/api", "text/csv", None)
        assert is_file_like("https://ex.it/api", "application/json", None)

    @pytest.mark.pure_unit
    def test_not_file_like(self):
        assert not is_file_like("https://ex.it/page", "text/html", None)


class TestIsHtmlContent:
    """pure_unit: rilevamento content-type HTML."""

    @pytest.mark.pure_unit
    def test_html(self):
        assert is_html_content("text/html")
        assert is_html_content("application/xhtml+xml")

    @pytest.mark.pure_unit
    def test_not_html(self):
        assert not is_html_content("text/csv")
        assert not is_html_content(None)


class TestFilenameFromContentDisposition:
    """pure_unit: estrazione filename da Content-Disposition."""

    @pytest.mark.pure_unit
    def test_quoted(self):
        assert filename_from_content_disposition('attachment; filename="data.csv"') == "data.csv"

    @pytest.mark.pure_unit
    def test_unquoted(self):
        assert filename_from_content_disposition("attachment; filename=data.csv") == "data.csv"

    @pytest.mark.pure_unit
    def test_rfc5987(self):
        result = filename_from_content_disposition("attachment; filename*=UTF-8''dati%202024.csv")
        assert result == "dati 2024.csv"

    @pytest.mark.pure_unit
    def test_none(self):
        assert filename_from_content_disposition(None) is None
        assert filename_from_content_disposition("") is None
