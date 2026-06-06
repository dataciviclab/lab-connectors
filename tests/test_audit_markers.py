"""
Test per audit_markers — contratto CLI + importable module.

Contratto:
  collect_tests()   produce risultati strutturati da file test_*.py
  main()            CLI entry point con exit code corretto
  test functions    hanno marker obbligatori (policy, contract, etc.)
"""

from pathlib import Path

import pytest

from lab_connectors.testing.audit_markers import (
    MARKERS,
    build_parser,
    collect_tests,
    main,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_test(p: Path, name: str, body: str) -> Path:
    f = p / name
    f.write_text(body)
    return f


# ---------------------------------------------------------------------------
# TestCollector
# ---------------------------------------------------------------------------


class TestTestCollector:
    @pytest.mark.pure_unit
    def test_detects_marker_on_function(self, tmp_path: Path) -> None:
        src = """
import pytest

def test_something():
    pass

@pytest.mark.pure_unit
def test_isolated():
    pass
"""
        _write_test(tmp_path, "test_example.py", src)
        results = collect_tests(tmp_path)
        assert len(results) == 2
        by_name = {r["test"]: r for r in results}
        assert by_name["test_something"]["unmarked"] is True
        assert by_name["test_isolated"]["unmarked"] is False
        assert by_name["test_isolated"]["markers"] == ["pure_unit"]

    @pytest.mark.pure_unit
    def test_module_level_marker(self, tmp_path: Path) -> None:
        src = """
import pytest

pytestmark = pytest.mark.contract

def test_api():
    pass

def test_another_api():
    pass
"""
        _write_test(tmp_path, "test_module.py", src)
        results = collect_tests(tmp_path)
        assert len(results) == 2
        for r in results:
            assert r["unmarked"] is False
            assert "contract" in r["markers"]

    @pytest.mark.pure_unit
    def test_module_level_marker_list(self, tmp_path: Path) -> None:
        src = """
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.smoke]

def test_multi():
    pass
"""
        _write_test(tmp_path, "test_multi.py", src)
        results = collect_tests(tmp_path)
        assert len(results) == 1
        assert results[0]["markers"] == ["contract", "smoke"]

    @pytest.mark.pure_unit
    def test_class_based_tests(self, tmp_path: Path) -> None:
        src = """
import pytest

class TestSuite:
    @pytest.mark.policy
    def test_rule(self):
        pass

    def test_unmarked_in_class(self):
        pass
"""
        _write_test(tmp_path, "test_class.py", src)
        results = collect_tests(tmp_path)
        assert len(results) == 2
        by_name = {r["test"]: r for r in results}
        assert by_name["test_rule"]["markers"] == ["policy"]
        assert by_name["test_unmarked_in_class"]["unmarked"] is True

    @pytest.mark.pure_unit
    def test_skips_conftest(self, tmp_path: Path) -> None:
        _write_test(tmp_path, "conftest.py", "def pytest_configure(): pass")
        _write_test(tmp_path, "test_real.py", "def test_thing(): pass")
        results = collect_tests(tmp_path)
        assert len(results) == 1
        assert results[0]["test"] == "test_thing"

    @pytest.mark.pure_unit
    def test_file_filter(self, tmp_path: Path) -> None:
        _write_test(tmp_path, "test_a.py", "def test_a(): pass")
        _write_test(tmp_path, "test_b.py", "def test_b(): pass")
        results = collect_tests(tmp_path, file_filter=["test_a.py"])
        assert len(results) == 1
        assert results[0]["test"] == "test_a"

    @pytest.mark.pure_unit
    def test_ignores_non_marker_decorators(self, tmp_path: Path) -> None:
        src = """
import pytest

@pytest.fixture
def fix(): pass

@pytest.mark.pure_unit
def test_with_fixture(fix):
    pass
"""
        _write_test(tmp_path, "test_fixture.py", src)
        results = collect_tests(tmp_path)
        assert len(results) == 1
        assert results[0]["markers"] == ["pure_unit"]

    @pytest.mark.pure_unit
    def test_subdirectory_tests(self, tmp_path: Path) -> None:
        sub = tmp_path / "http"
        sub.mkdir()
        _write_test(tmp_path, "test_root.py", "def test_root(): pass")
        _write_test(
            sub,
            "test_http.py",
            """
import pytest
@pytest.mark.adapter
def test_http_call(): pass
""",
        )
        results = collect_tests(tmp_path)
        assert len(results) == 2
        by_file = {r["file"]: r for r in results}
        assert "http/test_http.py" in by_file
        assert by_file["http/test_http.py"]["markers"] == ["adapter"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestMain:
    @pytest.mark.pure_unit
    def test_no_args_shows_help(self) -> None:
        with pytest.raises(SystemExit) as exc:
            main([])
        assert exc.value.code == 2  # argparse error

    @pytest.mark.pure_unit
    def test_ok_all_marked(self, tmp_path: Path) -> None:
        _write_test(
            tmp_path,
            "test_ok.py",
            """
import pytest
@pytest.mark.pure_unit
def test_ok(): pass
""",
        )
        code = main([str(tmp_path)])
        assert code == 0

    @pytest.mark.pure_unit
    def test_diff_exits_1_on_unmarked(self, tmp_path: Path) -> None:
        _write_test(tmp_path, "test_bad.py", "def test_bad(): pass")
        code = main([str(tmp_path), "--diff"])
        assert code == 1

    @pytest.mark.pure_unit
    def test_diff_ok_when_marked(self, tmp_path: Path) -> None:
        _write_test(
            tmp_path,
            "test_good.py",
            """
import pytest
@pytest.mark.contract
def test_good(): pass
""",
        )
        code = main([str(tmp_path), "--diff"])
        assert code == 0

    @pytest.mark.pure_unit
    def test_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _write_test(tmp_path, "test_json.py", "def test_json(): pass")
        code = main([str(tmp_path), "--json"])
        assert code == 0
        captured = capsys.readouterr()
        import json

        data = json.loads(captured.out)
        assert data["total"] == 1
        assert data["unmarked"] == 1

    @pytest.mark.pure_unit
    def test_bad_directory(self) -> None:
        code = main(["/nonexistent/path"])
        assert code == 2

    @pytest.mark.pure_unit
    def test_file_filter_via_cli(self, tmp_path: Path) -> None:
        _write_test(tmp_path, "test_a.py", "def test_a(): pass")
        _write_test(
            tmp_path,
            "test_b.py",
            """
import pytest
@pytest.mark.smoke
def test_b(): pass
""",
        )
        code = main([str(tmp_path), "--diff", "--files", "test_a.py"])
        assert code == 1  # test_a.py is unmarked
        code = main([str(tmp_path), "--diff", "--files", "test_b.py"])
        assert code == 0  # test_b.py is marked


# ---------------------------------------------------------------------------
# Module contract
# ---------------------------------------------------------------------------


class TestModuleContract:
    @pytest.mark.contract
    def test_markers_set_is_complete(self) -> None:
        """MARKERS contiene esattamente i 6 marker ufficiali."""
        assert MARKERS == {"contract", "policy", "regression", "adapter", "pure_unit", "smoke"}

    @pytest.mark.contract
    def test_build_parser_returns_parser(self) -> None:
        parser = build_parser()
        assert parser is not None
        args = parser.parse_args(["/some/dir", "--diff", "--json", "--files", "a.py", "b.py"])
        assert args.tests_dir == "/some/dir"
        assert args.diff is True
        assert args.json is True
        assert args.files == ["a.py", "b.py"]

    @pytest.mark.contract
    def test_collect_tests_returns_list(self, tmp_path: Path) -> None:
        _write_test(tmp_path, "test_contract.py", "def test_empty(): pass")
        results = collect_tests(tmp_path)
        assert isinstance(results, list)
        assert len(results) >= 0
