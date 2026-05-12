"""Tests per lab_connectors.duckdb."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import duckdb
import pytest

from lab_connectors.duckdb import safe_connect


class TestSafeConnect:
    """safe_connect — caso base (stdlib logging, no mcp)."""

    def test_basic_query(self) -> None:
        """Esecuzione query base su :memory:."""
        with safe_connect(":memory:") as con:
            result = con.execute("SELECT 1 AS x").fetchall()
        assert result == [(1,)]

    def test_multiple_connections(self) -> None:
        """Due connessioni indipendenti."""
        with safe_connect(":memory:") as c1:
            c1.execute("CREATE TABLE t (v INTEGER)")
            c1.execute("INSERT INTO t VALUES (42)")
            with safe_connect(":memory:") as c2:
                c2.execute("CREATE TABLE t (v INTEGER)")
                c2.execute("INSERT INTO t VALUES (99)")
                assert c2.execute("SELECT v FROM t").fetchall() == [(99,)]
            assert c1.execute("SELECT v FROM t").fetchall() == [(42,)]

    def test_read_only_forbids_write(self, tmp_path: pytest.TempPathFactory) -> None:
        """read_only=True impedisce scrittura su database su file."""
        db_path = tmp_path / "readonly.duckdb"
        # Prima crea il database
        with safe_connect(str(db_path)) as con:
            con.execute("CREATE TABLE t (v INTEGER)")
            con.execute("INSERT INTO t VALUES (1)")
        # Poi riapri in read-only — la scrittura deve fallire
        with safe_connect(str(db_path), read_only=True) as con:
            with pytest.raises(Exception, match="read.only"):
                con.execute("INSERT INTO t VALUES (2)")

    def test_file_database(self, tmp_path: pytest.TempPathFactory) -> None:
        """Connessione a file database."""
        db_path = tmp_path / "test.duckdb"
        with safe_connect(str(db_path)) as con:
            con.execute("CREATE TABLE t (v INTEGER)")
            con.execute("INSERT INTO t VALUES (1)")
        # Riapri e verifica persistenza
        with safe_connect(str(db_path)) as con:
            result = con.execute("SELECT v FROM t").fetchall()
        assert result == [(1,)]


class TestSafeConnectErrors:
    """safe_connect — error handling (no mcp)."""

    @patch("lab_connectors.duckdb.core._MCP_ERROR", None)
    def test_invalid_path_raises(self) -> None:
        """Path invalido solleva eccezione DuckDB."""
        # duckdb.connect solleva duckdb.IOException su path non esistente
        with pytest.raises(duckdb.IOException):
            with safe_connect("/nonexistent/dir/db.duckdb"):
                pass

    @patch("lab_connectors.duckdb.core._MCP_ERROR", None)
    @patch("lab_connectors.duckdb.core._ERROR_CODE_DUCKDB", None)
    def test_query_error_propagates(self) -> None:
        """Errore SQL propaga eccezione (senza MCP)."""
        with pytest.raises(duckdb.CatalogException, match="Catalog Error"):
            with safe_connect(":memory:") as con:
                con.execute("SELECT * FROM nonexistent_table").fetchall()

    @patch("lab_connectors.duckdb.core._MCP_ERROR", None)
    @patch("lab_connectors.duckdb.core._ERROR_CODE_DUCKDB", None)
    def test_error_closes_connection(self) -> None:
        """Errore nel context manager chiude comunque la connessione (senza MCP)."""
        con_ref = None
        with pytest.raises(duckdb.ParserException):
            with safe_connect(":memory:") as con:
                con_ref = con
                con.execute("INVALID SQL")
        # La connessione deve essere chiusa
        with pytest.raises(duckdb.ConnectionException):
            con_ref.execute("SELECT 1")


class TestSafeConnectMcp:
    """safe_connect — con McpLogger/McpError disponibili."""

    def test_with_tool_name_uses_mcp_logger(self) -> None:
        """tool_name attiva McpLogger (mock)."""
        mock_logger = MagicMock()
        mock_get_logger = MagicMock(return_value=mock_logger)

        with patch(
            "lab_connectors.duckdb.core._MCP_LOGGER", mock_get_logger
        ), patch("lab_connectors.duckdb.core._MCP_ERROR", Exception), patch(
            "lab_connectors.duckdb.core._ERROR_CODE_DUCKDB", "duckdb_error"
        ):
            with safe_connect(":memory:", tool_name="test_tool"):
                pass

        assert mock_get_logger.called
        assert mock_logger.info.called

    def test_mcp_error_logged_on_failure(self) -> None:
        """Con mcp attivo, errore viene loggato via McpLogger."""

        class _FakeMcpError(RuntimeError):
            """Fake McpError che accetta (code, message) come McpError reale."""

            def __init__(self, code: str, message: str) -> None:
                super().__init__(f"[{code}] {message}")
                self.code = code
                self.message = message

        mock_logger = MagicMock()
        mock_get_logger = MagicMock(return_value=mock_logger)

        with patch(
            "lab_connectors.duckdb.core._MCP_LOGGER", mock_get_logger
        ), patch("lab_connectors.duckdb.core._MCP_ERROR", _FakeMcpError), patch(
            "lab_connectors.duckdb.core._ERROR_CODE_DUCKDB", "duckdb_error"
        ):
            with pytest.raises(_FakeMcpError):
                with safe_connect(":memory:", tool_name="fail_tool") as con:
                    con.execute("INVALID")

        assert mock_logger.error.called
