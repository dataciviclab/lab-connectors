"""Test per lab_connectors.http.sparql — unit test su logica pura.

I test HTTP veri (execute_sparql su endpoint reale) sono esclusi:
dipendono dalla reachability dell'endpoint e da rate limiting.
Qui testiamo solo funzioni pure e logica di costruzione query.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from lab_connectors.http.sparql import (
    _binding_value,
    _bindings_to_csv,
    _build_schema_list,
    _compact_uri,
    _ensure_str_list,
    _looks_like_csv,
    discover_graphs,
    execute_sparql,
    fetch_csv,
    infer_schema,
)


@pytest.mark.pure_unit
class TestPureFunctions:
    """Funzioni di utilità pura (nessuna HTTP)."""

    @pytest.mark.pure_unit
    def test_compact_uri_fragment(self):
        assert _compact_uri("http://ex.org/ns#name") == "name"

    @pytest.mark.pure_unit
    def test_compact_uri_path(self):
        assert _compact_uri("http://dati.senato.it/osr/Senatore") == "Senatore"

    @pytest.mark.pure_unit
    def test_compact_uri_empty(self):
        assert _compact_uri("") == ""

    @pytest.mark.pure_unit
    def test_compact_uri_none(self):
        assert _compact_uri(None) == ""

    @pytest.mark.pure_unit
    def test_binding_value_present(self):
        b = {"g": {"type": "uri", "value": "http://test.it/g1"}}
        assert _binding_value(b, "g") == "http://test.it/g1"

    @pytest.mark.pure_unit
    def test_binding_value_missing_key(self):
        assert _binding_value({}, "x") is None

    @pytest.mark.pure_unit
    def test_binding_value_missing_value(self):
        b = {"g": {"type": "uri"}}
        assert _binding_value(b, "g") is None

    @pytest.mark.pure_unit
    def test_build_schema_list(self):
        bindings = [
            {"pred": {"value": "http://ex.org/name"}, "cnt": {"value": "100"}},
            {"pred": {"value": "http://ex.org/age#val"}, "cnt": {"value": "50"}},
        ]
        schema = _build_schema_list(bindings)
        assert len(schema) == 2
        assert schema[0]["compact_name"] == "name"
        assert schema[0]["count"] == 100
        assert schema[1]["compact_name"] == "val"
        assert schema[1]["count"] == 50

    @pytest.mark.pure_unit
    def test_build_schema_list_empty(self):
        assert _build_schema_list([]) == []

    @pytest.mark.pure_unit
    def test_build_schema_list_invalid_count(self):
        bindings = [{"pred": {"value": "http://ex.org/x"}, "cnt": {"value": "abc"}}]
        schema = _build_schema_list(bindings)
        assert schema[0]["count"] == 0

    @pytest.mark.pure_unit
    def test_ensure_str_list(self):
        assert _ensure_str_list([1, "abc"]) == ["1", "abc"]

    @pytest.mark.pure_unit
    def test_ensure_str_list_empty(self):
        assert _ensure_str_list([]) == []

    @pytest.mark.pure_unit
    def test_looks_like_csv(self):
        assert _looks_like_csv(b"col1,col2\nval1,val2") is True

    @pytest.mark.pure_unit
    def test_looks_like_csv_html(self):
        assert _looks_like_csv(b"<html>") is False

    @pytest.mark.pure_unit
    def test_looks_like_csv_empty(self):
        assert _looks_like_csv(b"") is False

    @pytest.mark.pure_unit
    def test_bindings_to_csv_empty(self):
        assert _bindings_to_csv([]) == b""

    @pytest.mark.pure_unit
    def test_bindings_to_csv_single(self):
        result = _bindings_to_csv([
            {"pred": {"value": "http://ex.org/name"}, "cnt": {"value": "100"}},
        ])
        assert b"pred,cnt" in result
        assert b"http://ex.org/name,100" in result

    @pytest.mark.pure_unit
    def test_bindings_to_csv_multiple_columns(self):
        result = _bindings_to_csv([
            {"a": {"value": "1"}, "b": {"value": "x"}},
            {"a": {"value": "2"}, "b": {"value": "y"}},
        ])
        lines = result.decode().splitlines()
        assert lines[0] == "a,b"
        assert lines[1] == "1,x"
        assert lines[2] == "2,y"


@pytest.mark.contract
@patch("lab_connectors.http.sparql.execute_sparql")
class TestDiscoverGraphs:
    """discover_graphs() con execute_sparql mockato."""

    @pytest.mark.contract
    def test_discover_returns_filtered(self, mock_exec):
        mock_exec.return_value = [
            {"g": {"value": "http://dati.test.it/graph1"}},
            {"g": {"value": "http://dati.test.it/graph2"}},
            {"g": {"value": "http://localhost/graph"}},
            {"g": {"value": "http://dati.test.it/virtrdf/graph"}},
        ]
        graphs = discover_graphs(
            "https://example.test/sparql",
            timeout=30,
            prefix="http://dati.test.it/",
            blacklist=["localhost", "virtrdf"],
        )
        assert graphs == [
            "http://dati.test.it/graph1",
            "http://dati.test.it/graph2",
        ]

    @pytest.mark.contract
    def test_discover_empty(self, mock_exec):
        mock_exec.return_value = []
        graphs = discover_graphs("https://example.test/sparql")
        assert graphs == []

    @pytest.mark.contract
    def test_discover_no_filter(self, mock_exec):
        mock_exec.return_value = [
            {"g": {"value": "http://a.it/g1"}},
            {"g": {"value": "http://b.it/g2"}},
        ]
        graphs = discover_graphs("https://example.test/sparql")
        assert len(graphs) == 2


@pytest.mark.contract
@patch("lab_connectors.http.sparql.execute_sparql")
class TestInferSchema:
    """infer_schema() con execute_sparql mockato."""

    @pytest.mark.contract
    def test_infer_returns_schema(self, mock_exec):
        mock_exec.return_value = [
            {"pred": {"value": "http://ex.org/name"}, "cnt": {"value": "10"}},
            {"pred": {"value": "http://ex.org/age"}, "cnt": {"value": "8"}},
        ]
        schema = infer_schema("https://ex.test/sparql", "http://ex.test/g1", limit=5)
        assert len(schema) == 2
        assert schema[0]["compact_name"] == "name"

    @pytest.mark.contract
    def test_infer_empty(self, mock_exec):
        mock_exec.return_value = []
        assert infer_schema("https://ex.test/sparql", "http://ex.test/g1") == []


@pytest.mark.contract
class TestFetchCsvPagination:
    """Logica di paginazione di fetch_csv() — testata senza HTTP."""

    @pytest.mark.contract
    def test_has_custom_limit_no_pagination(self):
        """Se la query ha già LIMIT, fetch_csv fa una sola fetch."""
        with patch(
            "lab_connectors.http.sparql._fetch_csv_page",
            return_value=b"col\nval",
        ) as mock_page:
            result = fetch_csv(
                "https://ex.test/sparql",
                "SELECT * WHERE { ?s ?p ?o } LIMIT 5",
                pages=3, step=100,
            )
            assert mock_page.call_count == 1
            assert result == b"col\nval"

    @pytest.mark.contract
    def test_pagination_injects_limit_offset(self):
        """Senza LIMIT esplicito, inietta LIMIT/OFFSET."""
        captured = []

        def fake_page(endpoint, query, timeout):
            captured.append(query)
            # Abbastanza righe per non triggerare early stop (step=10 → 12+ righe)
            lines = "col\n" + "\n".join(f"val{i}" for i in range(15))
            return lines.encode()

        with patch(
            "lab_connectors.http.sparql._fetch_csv_page",
            side_effect=fake_page,
        ):
            fetch_csv(
                "https://ex.test/sparql",
                "SELECT ?s WHERE { ?s ?p ?o }",
                pages=2, step=10,
            )
            assert len(captured) == 2
            assert "LIMIT 10" in captured[0]
            assert "OFFSET 0" in captured[0]
            assert "LIMIT 10" in captured[1]
            assert "OFFSET 10" in captured[1]

    @pytest.mark.contract
    def test_pagination_with_order_by(self):
        """ORDER BY non deve bloccare l'iniezione di LIMIT/OFFSET (bug fix)."""
        captured = []

        def fake_page(endpoint, query, timeout):
            captured.append(query)
            lines = "col\n" + "\n".join(f"v{i}" for i in range(15))
            return lines.encode()

        with patch(
            "lab_connectors.http.sparql._fetch_csv_page",
            side_effect=fake_page,
        ):
            fetch_csv(
                "https://ex.test/sparql",
                "SELECT ?s WHERE { ?s ?p ?o } ORDER BY ?s",
                pages=2, step=10,
            )
            assert len(captured) == 2
            assert "LIMIT 10" in captured[0]
            assert "OFFSET 0" in captured[0]
            assert "LIMIT 10" in captured[1]
            assert "OFFSET 10" in captured[1]

    @pytest.mark.contract
    def test_pagination_skips_header_on_page_2(self):
        """La seconda pagina concatena senza header duplicato."""
        call = [0]

        def fake_page(endpoint, query, timeout):
            call[0] += 1
            lines = "col\n" + "\n".join(
                f"val{i}" for i in range(5)
            )
            return lines.encode()

        with patch(
            "lab_connectors.http.sparql._fetch_csv_page",
            side_effect=fake_page,
        ):
            result = fetch_csv(
                "https://ex.test/sparql",
                "SELECT ?s WHERE { ?s ?p ?o }",
                pages=2, step=2,
            )
            lines = result.decode().splitlines()
            assert lines[0] == "col"  # header una volta
            assert lines[1:] == ["val0", "val1", "val2", "val3", "val4",
                                 "val0", "val1", "val2", "val3", "val4"]


@pytest.mark.contract
class TestExecuteSparqlErrorHandling:
    """execute_sparql() — solo edge case di errore."""

    @pytest.mark.contract
    def test_execute_empty_bindings(self):
        """Bindings vuoti non sono errore."""
        with patch(
            "lab_connectors.http.sparql._sparql_post",
            return_value=[],
        ):
            result = execute_sparql("https://ex.test/sparql", "SELECT * WHERE { }")
            assert result == []
