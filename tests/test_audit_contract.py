"""
Test per audit_contract — contratto CLI + importable module.

Contratto:
  scan_file()        produce violazioni strutturate da file Python
  scan_path()        scansiona ricorsivamente directory
  main()             CLI entry point con exit code corretto
  test functions     proteggono pattern di bypass reali
"""

from pathlib import Path

import pytest

from lab_connectors.testing.audit_contract import (
    ContractViolation,
    build_parser,
    main,
    scan_file,
    scan_path,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_py(p: Path, name: str, body: str) -> Path:
    f = p / name
    f.write_text(body)
    return f


# ---------------------------------------------------------------------------
# scan_file
# ---------------------------------------------------------------------------


class TestScanFile:
    @pytest.mark.pure_unit
    def test_clean_file_returns_empty(self, tmp_path: Path) -> None:
        f = _write_py(tmp_path, "ok.py", "x = 1\n")
        assert scan_file(f) == []

    @pytest.mark.pure_unit
    def test_duckdb_connect_detected(self, tmp_path: Path) -> None:
        src = """
import duckdb
con = duckdb.connect(":memory:")
con.execute("SELECT 1")
con.close()
"""
        f = _write_py(tmp_path, "test_x.py", src)
        viols = scan_file(f)
        codes = [v.code for v in viols]
        assert "DIRECT_DUCKDB_CONNECT" in codes

    @pytest.mark.pure_unit
    def test_monkeypatch_http_client_detected(self, tmp_path: Path) -> None:
        src = """
def test_get(monkeypatch):
    monkeypatch.setattr(HttpClient, "get", fake_get)
    monkeypatch.setattr(HttpClient, "head", fake_head)
    monkeypatch.setattr(HttpClient, "post", fake_post)
"""
        f = _write_py(tmp_path, "test_plugin.py", src)
        viols = scan_file(f)
        codes = [v.code for v in viols]
        assert "MONKEYPATCH_HTTP_CLIENT" in codes
        assert len([v for v in viols if v.code == "MONKEYPATCH_HTTP_CLIENT"]) == 3

    @pytest.mark.pure_unit
    def test_fake_response_class_detected(self, tmp_path: Path) -> None:
        src = """
class _FakeResponse:
    def __init__(self):
        self.status_code = 200
"""
        f = _write_py(tmp_path, "test_x.py", src)
        viols = scan_file(f)
        assert any(v.code == "FAKE_RESPONSE_CLASS" for v in viols)

    @pytest.mark.pure_unit
    def test_import_requests_in_source_detected(self, tmp_path: Path) -> None:
        src = "import requests\n"
        f = _write_py(tmp_path, "plugin.py", src)
        viols = scan_file(f)
        assert any(v.code == "REQUESTS_IMPORT_SOURCE" for v in viols)

    @pytest.mark.pure_unit
    def test_import_requests_in_test_ignored(self, tmp_path: Path) -> None:
        src = "import requests\n"
        f = _write_py(tmp_path, "test_plugin.py", src)
        viols = scan_file(f)
        # excluded via exclude_patterns matching /tests/ and /test_
        assert all(v.code != "REQUESTS_IMPORT_SOURCE" for v in viols)

    @pytest.mark.pure_unit
    def test_bucket_clean_hardcoded(self, tmp_path: Path) -> None:
        src = 'bucket = "dataciviclab-clean"\n'
        f = _write_py(tmp_path, "script.py", src)
        viols = scan_file(f)
        assert any(v.code == "BUCKET_CLEAN_HARDCODED" for v in viols)

    @pytest.mark.pure_unit
    def test_bucket_mart_hardcoded(self, tmp_path: Path) -> None:
        src = 'url = "dataciviclab-mart/something"\n'
        f = _write_py(tmp_path, "script.py", src)
        viols = scan_file(f)
        assert any(v.code == "BUCKET_MART_HARDCODED" for v in viols)

    @pytest.mark.pure_unit
    def test_empty_file_returns_empty(self, tmp_path: Path) -> None:
        f = _write_py(tmp_path, "empty.py", "")
        assert scan_file(f) == []

    @pytest.mark.pure_unit
    def test_non_python_file_skipped(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.write_text("duckdb.connect(")
        assert scan_file(f) == []


# ---------------------------------------------------------------------------
# scan_path (directory recursion)
# ---------------------------------------------------------------------------


class TestScanPath:
    @pytest.mark.pure_unit
    def test_scan_directory_finds_violations(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "test_a.py", "duckdb.connect(':memory:')\n")
        _write_py(tmp_path, "test_b.py", "x = 1\n")
        viols = scan_path(tmp_path)
        assert len(viols) == 1
        assert viols[0].code == "DIRECT_DUCKDB_CONNECT"

    @pytest.mark.pure_unit
    def test_skips_git_directory(self, tmp_path: Path) -> None:
        git = tmp_path / ".git"
        git.mkdir()
        _write_py(git, "hook.py", "duckdb.connect(':memory:')\n")
        viols = scan_path(tmp_path)
        assert all(v.code != "DIRECT_DUCKDB_CONNECT" for v in viols)

    @pytest.mark.pure_unit
    def test_skips_venv(self, tmp_path: Path) -> None:
        venv = tmp_path / ".venv"
        venv.mkdir()
        _write_py(venv, "lib.py", "duckdb.connect(':memory:')\n")
        viols = scan_path(tmp_path)
        assert all(v.code != "DIRECT_DUCKDB_CONNECT" for v in viols)

    @pytest.mark.pure_unit
    def test_violation_has_all_fields(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "test_x.py", 'import duckdb\ncon = duckdb.connect(":memory:")\n')
        viols = scan_path(tmp_path)
        assert len(viols) >= 1
        v = viols[0]
        assert v.file.endswith("test_x.py")
        assert isinstance(v.line, int) and v.line > 0
        assert v.code == "DIRECT_DUCKDB_CONNECT"
        assert v.severity == "error"
        assert v.found
        assert v.suggestion
        assert v.description


# ---------------------------------------------------------------------------
# CLI (main/build_parser)
# ---------------------------------------------------------------------------


class TestCLI:
    @pytest.mark.pure_unit
    def test_parser_builds(self) -> None:
        parser = build_parser()
        assert parser is not None

    @pytest.mark.pure_unit
    def test_scan_clean_dir_exit_0(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "ok.py", "x = 1\n")
        code = main(["scan", str(tmp_path)])
        assert code == 0

    @pytest.mark.pure_unit
    def test_scan_violations_no_fail_exit_0(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "test_x.py", "duckdb.connect(':memory:')\n")
        # No --fail, should exit 0 even with violations
        code = main(["scan", str(tmp_path)])
        assert code == 0

    @pytest.mark.pure_unit
    def test_scan_violations_with_fail_exit_1(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "test_x.py", "duckdb.connect(':memory:')\n")
        code = main(["scan", str(tmp_path), "--fail"])
        assert code == 1

    @pytest.mark.pure_unit
    def test_json_output_valid(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        _write_py(tmp_path, "test_x.py", "duckdb.connect(':memory:')\n")
        code = main(["scan", str(tmp_path), "--json"])
        assert code == 0
        import json

        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["code"] == "DIRECT_DUCKDB_CONNECT"

    @pytest.mark.pure_unit
    def test_scan_nonexistent_path(self, tmp_path: Path) -> None:
        code = main(["scan", str(tmp_path / "nope")])
        assert code == 0  # no crash, simply nothing to scan

    @pytest.mark.pure_unit
    def test_no_command_shows_help(self) -> None:
        with pytest.raises(SystemExit):
            main([])


# ---------------------------------------------------------------------------
# Violation dataclass
# ---------------------------------------------------------------------------


class TestContractViolation:
    @pytest.mark.pure_unit
    def test_to_dict(self) -> None:
        v = ContractViolation(
            file="test.py",
            line=42,
            code="DIRECT_DUCKDB_CONNECT",
            severity="error",
            found="duckdb.connect(",
            suggestion="Usare safe_connect()",
            description="test",
        )
        d = v.to_dict()
        assert d["file"] == "test.py"
        assert d["code"] == "DIRECT_DUCKDB_CONNECT"
        assert d["severity"] == "error"
