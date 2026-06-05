#!/usr/bin/env python3
"""Audit test markers — cross-repo CLI & importable module.

Detects ``@pytest.mark.{contract,policy,regression,adapter,pure_unit,smoke}``
on test functions via AST parsing.  No runtime dependencies beyond stdlib.

Usage (CLI)::

    audit-test-markers tests/                        # audit entire dir
    audit-test-markers tests/ --diff                 # exit 1 if any unmarked
    audit-test-markers tests/ --json                 # machine-readable
    audit-test-markers tests/ --files f1.py f2.py    # specific files

Usage (import)::

    from lab_connectors.testing.audit_markers import collect_tests
    results = collect_tests(Path("tests/"))
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

MARKERS = {"contract", "policy", "regression", "adapter", "pure_unit", "smoke"}
_MARKER_RE = re.compile(r"mark\.(\w+)")


class TestCollector(ast.NodeVisitor):
    """Collect test functions and their markers via AST.

    Detects markers from:
    - ``@pytest.mark.xxx`` decorators on test functions/methods
    - Module-level ``pytestmark = pytest.mark.xxx`` or
      ``pytestmark = [pytest.mark.xxx, pytest.mark.yyy]``
    """

    __test__ = False  # prevent pytest from collecting this as a test class

    def __init__(self) -> None:
        self.results: list[dict[str, Any]] = []
        self._module_markers: set[str] = set()

    def visit_Module(self, node: ast.Module) -> None:
        """Collect module-level pytestmark, then scan test functions/classes."""
        self._collect_module_markers(node)
        for stmt in ast.iter_child_nodes(node):
            if isinstance(stmt, ast.FunctionDef) and stmt.name.startswith("test_"):
                self._visit_test_function(stmt)
            elif isinstance(stmt, ast.ClassDef):
                for child in ast.iter_child_nodes(stmt):
                    if isinstance(child, ast.FunctionDef) and child.name.startswith("test_"):
                        self._visit_test_function(child)
        self.generic_visit(node)

    def _collect_module_markers(self, node: ast.Module) -> None:
        """Extract ``pytestmark`` assignments at module level."""
        for stmt in ast.iter_child_nodes(node):
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name) and target.id == "pytestmark":
                        self._add_marker_from_value(stmt.value)

    def _add_marker_from_value(self, value: ast.expr) -> None:
        """Add marker(s) from a single value or a list of values."""
        if isinstance(value, ast.List):
            for elt in value.elts:
                m = self._get_marker_name(elt)
                if m:
                    self._module_markers.add(m)
        else:
            m = self._get_marker_name(value)
            if m:
                self._module_markers.add(m)

    def _visit_test_function(self, node: ast.FunctionDef) -> None:
        """Extract markers from a single test function."""
        markers: set[str] = set()
        markers.update(self._module_markers)
        for decorator in reversed(node.decorator_list):
            marker = self._get_marker_name(decorator)
            if marker:
                markers.add(marker)
        self.results.append(
            {
                "test": node.name,
                "markers": sorted(markers & MARKERS),
                "missing": sorted(MARKERS - markers),
                "unmarked": not bool(markers & MARKERS),
            }
        )

    def _get_marker_name(self, node: ast.expr) -> str | None:
        """Extract Lab marker name from a decorator via ``ast.unparse`` + regex."""
        try:
            src = ast.unparse(node)
            m = _MARKER_RE.search(src)
            if m and m.group(1) in MARKERS:
                return m.group(1)
        except Exception:
            pass
        return None


def collect_tests(tests_dir: Path, file_filter: list[str] | None = None) -> list[dict[str, Any]]:
    """Collect all test functions from ``test_*.py`` files in *tests_dir* (recursive).

    Args:
        tests_dir: Directory containing test files.
        file_filter: Optional list of filenames to restrict scanning to.

    Returns:
        List of dicts with keys ``test``, ``markers``, ``missing``, ``unmarked``, ``file``.
    """
    results: list[dict[str, Any]] = []

    # Top-level files
    for fpath in sorted(tests_dir.glob("test_*.py")):
        _scan_file(fpath, fpath.name, file_filter, results)

    # Subdirectories (e.g. ``tests/http/``)
    for subdir in sorted(tests_dir.iterdir()):
        if not subdir.is_dir() or subdir.name.startswith("_") or subdir.name == "__pycache__":
            continue
        for fpath in sorted(subdir.glob("test_*.py")):
            _scan_file(fpath, str(Path(subdir.name) / fpath.name), file_filter, results)

    return results


def _scan_file(
    fpath: Path,
    display_name: str,
    file_filter: list[str] | None,
    results: list[dict[str, Any]],
) -> None:
    """Parse a single test file and append results."""
    if fpath.name == "conftest.py":
        return
    if file_filter and Path(fpath).name not in file_filter:
        return
    try:
        tree = ast.parse(fpath.read_text(), filename=fpath.name)
    except SyntaxError:
        return
    visitor = TestCollector()
    visitor.visit(tree)
    for r in visitor.results:
        r["file"] = display_name
        results.append(r)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser (useful for testing)."""
    parser = argparse.ArgumentParser(
        description="Audit test markers in any repo's test directory.",
    )
    parser.add_argument("tests_dir", type=str, help="Path to tests/ directory")
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Exit 1 if any test is unmarked (for CI gate)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Machine-readable JSON output",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=None,
        help="Check only specific test files (for PR diff checks)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.  Returns exit code.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns:
        0 if all tests have markers (or ``--diff`` not set),
        1 if any test is unmarked (only with ``--diff``).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    tests_path = Path(args.tests_dir)
    if not tests_path.is_dir():
        print(f"ERROR: directory not found: {tests_path}", file=sys.stderr)
        return 2

    results = collect_tests(tests_path, args.files)
    unmarked = [r for r in results if r["unmarked"]]
    marked = [r for r in results if not r["unmarked"]]

    if args.json:
        print(
            json.dumps(
                {
                    "total": len(results),
                    "marked": len(marked),
                    "unmarked": len(unmarked),
                    "tests": results,
                },
                indent=2,
            )
        )
    else:
        print("=== Test Marker Audit ===")
        print(f"Tests: {len(results)} | Marked: {len(marked)} | Unmarked: {len(unmarked)}")
        print()
        if unmarked:
            print(f"--- UNMARKED TESTS ({len(unmarked)}) ---")
            for r in unmarked:
                print(f"  {r['file']}::{r['test']}")
            print()
            print("Suggested markers (pick one per test):")
            print("  @pytest.mark.contract  — public interface, artifact format, CLI output")
            print("  @pytest.mark.policy    — Lab rule not derivable from source code")
            print("  @pytest.mark.regression — documented bug fix (link issue/PR)")
            print("  @pytest.mark.adapter   — external service adapter logic")
            print("  @pytest.mark.pure_unit  — pure logic, zero side effects")
            print("  @pytest.mark.smoke     — golden path end-to-end")
            print()
        if not unmarked:
            print("All tests have markers. OK")

    if args.diff and unmarked:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
