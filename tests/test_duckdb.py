"""Tests per lab_connectors.duckdb.

``duckdb`` è extra opzionale ``[duckdb]`` — se non installato,
``pytest.importorskip`` salta tutti i test del modulo.
"""

from __future__ import annotations

import unittest.mock

import pytest

pytest.importorskip("duckdb")

import duckdb

from lab_connectors.duckdb import gcs_connect, safe_connect
from lab_connectors.duckdb.core import GCS_S3_CONFIG

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

    def test_memory_limit_default_is_2gb(self) -> None:
        """Default: memory_limit = 2GB (senza env)."""
        with safe_connect(":memory:") as con:
            limit = con.execute("SELECT current_setting('memory_limit')").fetchone()
        assert limit and "1.8 GiB" in str(limit[0])

    def test_memory_limit_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """DUCKDB_MEMORY_LIMIT sovrascrive il default 2GB."""
        monkeypatch.setenv("DUCKDB_MEMORY_LIMIT", "4GB")
        with safe_connect(":memory:") as con:
            limit = con.execute("SELECT current_setting('memory_limit')").fetchone()
        assert limit and "3.7 GiB" in str(limit[0])

    def test_memory_limit_config_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Il parametro config vince sull'env."""
        monkeypatch.setenv("DUCKDB_MEMORY_LIMIT", "4GB")
        with safe_connect(":memory:", config={"memory_limit": "1GB"}) as con:
            limit = con.execute("SELECT current_setting('memory_limit')").fetchone()
        assert limit and "953.6 MiB" in str(limit[0])


class TestSafeConnectErrors:
    """safe_connect — error handling."""

    def test_invalid_path_raises(self) -> None:
        """Path invalido solleva eccezione DuckDB."""
        with pytest.raises(duckdb.IOException), safe_connect("/nonexistent/dir/db.duckdb"):
            pass

    def test_query_error_propagates(self) -> None:
        """Errore SQL propaga eccezione originale."""
        with pytest.raises(duckdb.CatalogException, match="Catalog Error"):
            with safe_connect(":memory:") as con:
                con.execute("SELECT * FROM nonexistent_table").fetchall()

    def test_error_closes_connection(self) -> None:
        """Errore nel context manager chiude comunque la connessione."""
        con_ref = None
        with pytest.raises(duckdb.ParserException), safe_connect(":memory:") as con:
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

        with (
            unittest.mock.patch.object(
                duckdb.DuckDBPyConnection,
                "close",
                _broken_close,
            ),
            safe_connect(":memory:") as con,
        ):
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


class TestSafeConnectExtensions:
    """safe_connect — parametri extensions e config."""

    def test_default_backward_compat(self) -> None:
        """Nessun parametro = comportamento identico al passato."""
        with safe_connect() as con:
            r = con.execute("SELECT 1 AS x").fetchall()
        assert r == [(1,)]

    def test_httpfs_extension_loads(self) -> None:
        """Caricamento estensione httpfs (se disponibile)."""
        try:
            with safe_connect(extensions=["httpfs"]) as con:
                con.execute("SELECT 1")
        except duckdb.IOException as exc:
            if "HTTP" in str(exc) or "extension" in str(exc):
                pytest.skip("httpfs extension not available")
            raise

    def test_config_memory_limit(self) -> None:
        """Config DuckDB passata correttamente.

        DuckDB converte ``512 MB`` nel suo formato interno
        (es. ``'488.2 MiB'``). Verifichiamo che il setting sia
        stato applicato controllando il suffisso MiB.
        """
        with safe_connect(config={"memory_limit": "512MB"}) as con:
            row = con.execute(
                "SELECT value FROM duckdb_settings() WHERE name = 'memory_limit'"
            ).fetchone()
        assert row is not None
        value = str(row[0])
        assert value.endswith("MiB"), f"MiB atteso, ottenuto {value!r}"

    def test_unknown_extension_raises(self) -> None:
        """Estensione inesistente solleva eccezione."""
        with pytest.raises(duckdb.IOException):
            with safe_connect(extensions=["nonexistent_extension_xyz"]):
                pass


class TestDefaultConfig:
    """Configurazioni di default safe_connect."""

    def test_memory_limit_default_applied(self) -> None:
        """safe_connect applica memory_limit di default (~2 GB → ~1.8 GiB)."""
        import re

        with safe_connect() as con:
            row = con.execute(
                "SELECT value FROM duckdb_settings() WHERE name = 'memory_limit'"
            ).fetchone()
        assert row is not None
        value = str(row[0])
        match = re.match(r"^(\d+\.?\d*)\s*GiB", value)
        assert match is not None, f"Expected ~2 GiB, got {value!r}"
        gib_value = float(match.group(1))
        # 2 GB → ~1.8 GiB in DuckDB (binary conversion)
        assert 1.7 <= gib_value <= 1.9, f"Expected ~1.8 GiB, got {gib_value} GiB"

    def test_config_overrides_default(self) -> None:
        """Config esplicita sovrascrive memory_limit di default."""
        with safe_connect(config={"memory_limit": "512MB"}) as con:
            row = con.execute(
                "SELECT value FROM duckdb_settings() WHERE name = 'memory_limit'"
            ).fetchone()
        assert row is not None
        value = str(row[0])
        # 512MB → DuckDB mostra circa 488 MiB
        assert "488" in value or "512" in value

    def test_progress_bar_disabled(self) -> None:
        """safe_connect disabilita la progress bar."""
        with safe_connect() as con:
            row = con.execute(
                "SELECT value FROM duckdb_settings() WHERE name = 'enable_progress_bar'"
            ).fetchone()
        assert row is not None
        # disable_progress_bar ⇒ enable_progress_bar = false
        assert str(row[0]).lower() == "false"


class TestGcsConnect:
    """gcs_connect — helper per GCS S3 / locale."""

    def test_local_path_uses_plain_safe_connect(self) -> None:
        """Path locale non carica httpfs."""
        with gcs_connect(":memory:") as con:
            r = con.execute("SELECT 1 AS x").fetchall()
        assert r == [(1,)]

    @pytest.mark.parametrize("prefix", ["gs://", "gs:/"])
    def test_gs_url_routes_to_httpfs(self, prefix: str) -> None:
        """Path gs:// e gs:/ (anche glob multi-file) instradano su httpfs.

        I glob multi-year su HTTP generico non sono supportati da DuckDB;
        l'unica via è httpfs con config S3/GCS. ``gcs_connect`` deve quindi
        caricare httpfs per ``gs`` come già faceva per ``s3`` (pattern
        simmetrico: doppio e singolo slash).
        """
        with unittest.mock.patch("lab_connectors.duckdb.core.safe_connect") as mock_sc:
            with gcs_connect(f"{prefix}dataciviclab-clean/slug/*/*.parquet"):
                pass
        mock_sc.assert_called_once()
        kwargs = mock_sc.call_args.kwargs
        assert kwargs["extensions"] == ["httpfs"]
        assert kwargs["config"] == GCS_S3_CONFIG

    def test_https_url_does_not_load_httpfs(self) -> None:
        """Path https:// NON carica httpfs (lettura nativa stabile)."""
        with unittest.mock.patch("lab_connectors.duckdb.core.safe_connect") as mock_sc:
            with gcs_connect("https://storage.googleapis.com/dataciviclab-clean/x.parquet"):
                pass
        mock_sc.assert_called_once()
        kwargs = mock_sc.call_args.kwargs
        assert "extensions" not in kwargs

    def test_local_file_database(self, tmp_path: pytest.TempPathFactory) -> None:
        """gcs_connect con database DuckDB su file."""
        db_path = tmp_path / "test.duckdb"
        with gcs_connect("/local/file.parquet", database=str(db_path)) as con:
            con.execute("CREATE TABLE t (v INTEGER)")
            con.execute("INSERT INTO t VALUES (42)")
        with gcs_connect("/local/file.parquet", database=str(db_path)) as con:
            r = con.execute("SELECT v FROM t").fetchall()
        assert r == [(42,)]

    @pytest.mark.smoke
    def test_https_gcs_connect(self) -> None:
        """gcs_connect con HTTPS deve funzionare senza httpfs."""
        url = "https://storage.googleapis.com/dataciviclab-clean/catalog_inventory/catalog_inventory_latest.parquet"
        try:
            with gcs_connect(url) as con:
                row = con.execute(f"SELECT COUNT(*) FROM read_parquet('{url}')").fetchone()
                assert row is not None and row[0] > 0
        except duckdb.IOException:
            pytest.skip("GCS HTTP endpoint not reachable from this runner")
