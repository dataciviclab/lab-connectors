"""Tests per discovery.links — contratto: extract_data_links, group_links.

pure_unit: extract_data_links, group_links, extract_prefix, extract_years, resolve_format
"""

from __future__ import annotations

import pytest

from lab_connectors.discovery.links import (
    DataLink,
    extract_candidate_links,
    extract_data_links,
    extract_filename,
    extract_prefix,
    extract_years,
    group_links,
    resolve_format,
)


class TestExtractDataLinks:
    """pure_unit: estrazione link dati da HTML."""

    @pytest.mark.pure_unit
    def test_basic_formats(self):
        """Estrae CSV, XLSX, JSON, ZIP, RDF; ignora PDF e HTML."""
        html = """
            <a href="/data.csv">CSV</a>
            <a href="/data.xlsx">XLSX</a>
            <a href="/data.json">JSON</a>
            <a href="/data.zip">ZIP</a>
            <a href="/data.rdf">RDF</a>
            <a href="/about">HTML</a>
            <a href="/report.pdf">PDF</a>
        """
        links = extract_data_links("https://ex.it", html)
        assert len(links) == 5
        assert {lnk.format for lnk in links} == {"CSV", "XLSX", "JSON", "ZIP", "RDF"}

    @pytest.mark.pure_unit
    def test_liferay_urls_with_uuid_suffix(self):
        """URL Liferay: estensione come segmento, UUID in coda."""
        csv_url = "/portale/documents/20118/0/2023_Ind_AMMINISTR_01_IT.csv/45e7ec1b-d282-278d"
        xlsx_url = "/portale/documents/20118/0/2023_Metadati_Ind_FC90.xlsx/9e1fd560-98c5-4b2a"
        html = f'<a href="{csv_url}">CSV</a><a href="{xlsx_url}">XLSX</a>'
        links = extract_data_links("https://ex.it", html)
        assert len(links) == 2
        formats = {lnk.format for lnk in links}
        assert "CSV" in formats
        assert "XLSX" in formats

    @pytest.mark.pure_unit
    def test_liferay_does_not_false_positive_on_short_tail(self):
        """Non confondere un path con '.csv/' seguito da segmento corto."""
        html = '<a href="/docs/report.csv/v1">storto</a>'
        links = extract_data_links("https://ex.it", html)
        assert len(links) == 0

    @pytest.mark.pure_unit
    def test_skips_anchors_and_protocols(self):
        """Ignora ancore, mailto, tel, javascript."""
        html = """
            <a href="#section">X</a>
            <a href="mailto:a@b.it">X</a>
            <a href="tel:+39">X</a>
            <a href="javascript:void(0)">X</a>
        """
        assert extract_data_links("https://ex.it", html) == []

    @pytest.mark.pure_unit
    def test_resolves_relative_and_title(self):
        """URL relativi risolti, aria-label come title."""
        links = extract_data_links(
            "https://ex.it/dir/",
            '<a href="data.csv" aria-label="Report">x</a>',
        )
        assert links[0].url == "https://ex.it/dir/data.csv"
        assert links[0].title == "Report"

    @pytest.mark.pure_unit
    def test_prefix_and_years(self):
        """Prefisso e anni estratti dal filename."""
        links = extract_data_links(
            "https://ex.it",
            '<a href="REG_tipo_reddito_2025.csv">x</a>',
        )
        assert links[0].prefix == "REG"
        assert links[0].years == [2025]

    @pytest.mark.pure_unit
    def test_deduplicates_by_url(self):
        """Link duplicati vengono deduplicati."""
        html = """
            <a href="/data.csv">1</a>
            <a href="/data.csv">2</a>
        """
        links = extract_data_links("https://ex.it", html)
        assert len(links) == 1

    @pytest.mark.pure_unit
    def test_custom_data_extensions(self):
        """Estensioni custom sovrascrivono i default."""
        html = '<a href="/file.custom">x</a>'
        links = extract_data_links("https://ex.it", html, data_extensions={".custom"})
        assert len(links) == 1
        assert links[0].format == "CUSTOM"

    @pytest.mark.pure_unit
    def test_empty_html(self):
        """HTML vuoto → lista vuota."""
        assert extract_data_links("https://ex.it", "") == []


class TestGroupLinks:
    """pure_unit: raggruppamento link per prefisso."""

    @pytest.mark.pure_unit
    def test_single_group(self):
        """Stesso prefisso → un gruppo con anni e formati."""
        links = [
            DataLink(url="https://ex.it/REG_2024.csv", format="CSV", prefix="REG", years=[2024]),
            DataLink(url="https://ex.it/REG_2025.csv", format="CSV", prefix="REG", years=[2025]),
        ]
        groups = group_links(links)
        assert len(groups) == 1
        assert groups[0].group_id == "REG"
        assert groups[0].count == 2
        assert groups[0].year_range == [2024, 2025]

    @pytest.mark.pure_unit
    def test_multiple_groups(self):
        """Prefissi diversi → gruppi separati."""
        links = [
            DataLink(url="https://ex.it/REG_2024.csv", format="CSV", prefix="REG"),
            DataLink(url="https://ex.it/CLA_2024.csv", format="CSV", prefix="CLA"),
        ]
        groups = group_links(links)
        assert len(groups) == 2
        assert {g.group_id for g in groups} == {"REG", "CLA"}

    @pytest.mark.pure_unit
    def test_no_prefix_becomes_other(self):
        """Link senza prefisso → gruppo other."""
        groups = group_links([DataLink(url="https://ex.it/data.csv", format="CSV")])
        assert groups[0].group_id == "other"

    @pytest.mark.pure_unit
    def test_empty(self):
        """Lista vuota → lista vuota."""
        assert group_links([]) == []

    @pytest.mark.pure_unit
    def test_sorted_by_count_desc(self):
        """Gruppi ordinati per dimensione discendente."""
        links = [
            DataLink(url="https://ex.it/A_1.csv", format="CSV", prefix="A"),
            DataLink(url="https://ex.it/A_2.csv", format="CSV", prefix="A"),
            DataLink(url="https://ex.it/B_1.csv", format="CSV", prefix="B"),
        ]
        groups = group_links(links)
        assert groups[0].group_id == "A"
        assert groups[0].count == 2


class TestHelpers:
    """pure_unit: helper functions."""

    @pytest.mark.pure_unit
    def test_extract_filename(self):
        assert extract_filename("https://ex.it/path/data_2024.csv") == "data_2024"
        assert extract_filename("https://ex.it/data.csv") == "data"
        assert extract_filename("https://ex.it/path/file") == "file"

    @pytest.mark.pure_unit
    def test_extract_prefix_with_underscore(self):
        assert extract_prefix("REG_tipo_reddito") == "REG"
        assert extract_prefix("CLA_altro") == "CLA"

    @pytest.mark.pure_unit
    def test_extract_prefix_uppercase_run(self):
        assert extract_prefix("ABC123_dati") == "ABC123"
        assert extract_prefix("XY_file") == "XY"

    @pytest.mark.pure_unit
    def test_extract_prefix_fallback(self):
        """Fallback: primi 6 caratteri."""
        assert extract_prefix("abcdefgh") == "abcdef"

    @pytest.mark.pure_unit
    def test_extract_years(self):
        assert extract_years("data_2020_2023") == [2020, 2023]
        assert extract_years("report") == []
        assert extract_years("file_1999") == []  # solo 20xx

    @pytest.mark.pure_unit
    def test_resolve_format_standard(self):
        assert resolve_format("https://ex.it/data.csv") == "CSV"
        assert resolve_format("https://ex.it/data.XLSX") == "XLSX"
        assert resolve_format("https://ex.it/data.geojson") == "GEOJSON"

    @pytest.mark.pure_unit
    def test_resolve_format_liferay(self):
        url = "https://ex.it/docs/file.csv/45e7ec1b-d282-278d-de7b-73af"
        assert resolve_format(url) == "CSV"

    @pytest.mark.pure_unit
    def test_resolve_format_no_match(self):
        assert resolve_format("https://ex.it/page") is None
        assert resolve_format("https://ex.it/report.pdf") is None

    @pytest.mark.pure_unit
    def test_extract_candidate_links_legacy(self):
        """Legacy: ritorna solo URL."""
        html = '<a href="/data.csv">x</a><a href="/data.xlsx">y</a>'
        urls = extract_candidate_links("https://ex.it", html)
        assert len(urls) == 2
        assert all(u.startswith("https://ex.it/") for u in urls)
