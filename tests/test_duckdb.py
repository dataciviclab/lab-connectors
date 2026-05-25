# ruff: noqa: E402, I001
"""Tests per lab_connectors.duckdb.

``duckdb`` è extra opzionale ``[duckdb]`` — se non installato,
``pytest.importorskip`` salta tutti i test del modulo.
"""
from __future__ import annotations

import unittest.mock

import pytest

pytest.importorskip("duckdb")

import duckdb
from lab_connectors.duckdb import safe_connect

pytestmark = pytest.mark.contract


class TestSafeConnect:
    """safe_connect — caso base."""

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
    """safe_connect — error handling."""

    def test_invalid_path_raises(self) -> None:
        """Path invalido solleva eccezione DuckDB."""
        with pytest.raises(duckdb.IOException):
            with safe_connect("/nonexistent/dir/db.duckdb"):
                pass

    def test_query_error_propagates(self) -> None:
        """Errore SQL propaga eccezione originale."""
        with pytest.raises(duckdb.CatalogException, match="Catalog Error"):
            with safe_connect(":memory:") as con:
                con.execute("SELECT * FROM nonexistent_table").fetchall()

    def test_error_closes_connection(self) -> None:
        """Errore nel context manager chiude comunque la connessione."""
        con_ref = None
        with pytest.raises(duckdb.ParserException):
            with safe_connect(":memory:") as con:
                con_ref = con
                con.execute("INVALID SQL")
        # La connessione deve essere chiusa
        with pytest.raises(duckdb.ConnectionException):
            con_ref.execute("SELECT 1")

    def test_close_exception_is_silent(self) -> None:
        """Se con.close() solleva eccezione, safe_connect la ingoia.

        La finally di safe_connect prova con.close() ma se fallisce
        (es. connessione gia' chiusa), cattura l'eccezione con
        ``except Exception: pass``.

        Patcheddiamo duckdb.DuckDBPyConnection.close (via class) per
        far fallire TUTTE le close() durante il test e verifichiamo
        che safe_connect esca pulito.
        """
        original_close = duckdb.DuckDBPyConnection.close

        def _broken_close(self_conn: duckdb.DuckDBPyConnection) -> None:
            """close() che solleva eccezione dopo aver chiamato l'originale."""
            original_close(self_conn)
            raise RuntimeError("simulated close failure")

        with unittest.mock.patch.object(
            duckdb.DuckDBPyConnection, "close", _broken_close,
        ):
            with safe_connect(":memory:") as con:
                con.execute("SELECT 1")
        # Il test passa se non c'e' eccezione — siamo usciti dal context manager

    def test_already_closed_connection_is_silent(self) -> None:
        """safe_connect non fallisce se la connessione e' gia' chiusa.

        La finally chiama con.close() su una connessione gia' chiusa.
        DuckDB solleva ConnectionException ma safe_connect la ingoia.
        """
        with safe_connect(":memory:") as con:
            con.close()
        # Il test passa — siamo usciti dal context manager
