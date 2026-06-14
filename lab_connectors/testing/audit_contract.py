#!/usr/bin/env python3
"""Audit bypass patterns — cross-repo CLI & importable module.

Scansiona file Python per pattern che bypassano ``lab-connectors``
invece di usarne le API canoniche. Ogni violazione riporta file, linea,
codice e suggerimento.

Usage (CLI)::

    lab-connectors-audit scan tests/                          # scan directory
    lab-connectors-audit scan tests/ src/ --fail              # exit 1 on error
    lab-connectors-audit scan tests/ --json                   # machine-readable

Usage (import)::

    from lab_connectors.testing.audit_contract import scan_path, ContractViolation
    violations = scan_path(Path("tests/"))
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------


@dataclass
class BypassPattern:
    """A single bypass pattern to detect."""

    code: str
    severity: str  # "error" or "warning"
    regex: re.Pattern[str]
    suggestion: str
    description: str
    exclude_patterns: list[re.Pattern[str]] = field(default_factory=list)
    """File paths matching any of these are skipped."""


# Patterns that block CI
_ERROR_PATTERNS: list[BypassPattern] = [
    BypassPattern(
        code="DIRECT_DUCKDB_CONNECT",
        severity="error",
        regex=re.compile(r"duckdb\.connect\("),
        suggestion="Usare safe_connect() o gcs_connect() da lab_connectors.duckdb",
        description=(
            "duckdb.connect() diretto — perde memory_limit, progress_bar, chiusura automatica"
        ),
    ),
    BypassPattern(
        code="MONKEYPATCH_HTTP_CLIENT",
        severity="error",
        regex=re.compile(r'monkeypatch\.setattr\(\s*HttpClient\s*,\s*"(?:get|head|post)"'),
        suggestion="Usare FakeHttpClient da lab_connectors.testing",
        description="Mock manuale di HttpClient.get/head/post invece di FakeHttpClient",
    ),
    BypassPattern(
        code="FAKE_RESPONSE_CLASS",
        severity="error",
        regex=re.compile(r"class\s+_FakeResponse"),
        suggestion="Usare fake_response() da lab_connectors.testing",
        description="Definizione locale di _FakeResponse invece di fake_response()",
    ),
    BypassPattern(
        code="REQUESTS_IMPORT_SOURCE",
        severity="error",
        regex=re.compile(r"^import requests$", re.MULTILINE),
        suggestion="Usare HttpClient da lab_connectors.http",
        description="import requests in codice sorgente (non test): usare HttpClient",
        exclude_patterns=[
            re.compile(r"/tests/"),
            re.compile(r"/test_[^/]+\.py$"),
            re.compile(r"/conftest\.py$"),
            re.compile(r"__init__\.py$"),
            re.compile(r"/testing/"),
        ],
    ),
]

# Patterns that warn but don't block CI
_WARNING_PATTERNS: list[BypassPattern] = [
    BypassPattern(
        code="BUCKET_CLEAN_HARDCODED",
        severity="warning",
        regex=re.compile(r"dataciviclab-clean"),
        suggestion="Usare CLEAN_BUCKET da lab_connectors.gcs.paths",
        description="Bucket name dataciviclab-clean hardcoded",
        exclude_patterns=[
            re.compile(r"/\.git/"),
            re.compile(r"__pycache__"),
            re.compile(r"paths\.json$"),
        ],
    ),
    BypassPattern(
        code="BUCKET_MART_HARDCODED",
        severity="warning",
        regex=re.compile(r"dataciviclab-mart"),
        suggestion="Usare MART_BUCKET da lab_connectors.gcs.paths",
        description="Bucket name dataciviclab-mart hardcoded",
        exclude_patterns=[
            re.compile(r"/\.git/"),
            re.compile(r"__pycache__"),
            re.compile(r"paths\.json$"),
        ],
    ),
]

ALL_PATTERNS = _ERROR_PATTERNS + _WARNING_PATTERNS


# ---------------------------------------------------------------------------
# Violation model
# ---------------------------------------------------------------------------


@dataclass
class ContractViolation:
    """A single contract violation found during scan."""

    file: str
    line: int
    code: str
    severity: str
    found: str
    suggestion: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize violation to a JSON-compatible dict."""
        return {
            "file": self.file,
            "line": self.line,
            "code": self.code,
            "severity": self.severity,
            "found": self.found,
            "suggestion": self.suggestion,
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


def _should_exclude(file_path: Path, exclude_patterns: list[re.Pattern[str]]) -> bool:
    """Check if a file path matches any exclusion pattern."""
    str_path = file_path.as_posix()
    for pat in exclude_patterns:
        if pat.search(str_path):
            return True
    return False


def scan_file(
    file_path: Path, patterns: list[BypassPattern] | None = None
) -> list[ContractViolation]:
    """Scan a single file for contract violations.

    Args:
        file_path: Path to the Python file to scan.
        patterns: Patterns to check (default: ALL_PATTERNS).

    Returns:
        List of violations found (empty if clean).

    """
    if not file_path.is_file() or file_path.suffix != ".py":
        return []

    patterns = patterns or ALL_PATTERNS
    violations: list[ContractViolation] = []

    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return []

    str_path = file_path.as_posix()

    for pattern in patterns:
        if _should_exclude(file_path, pattern.exclude_patterns):
            continue
        for match in pattern.regex.finditer(text):
            line_number = text[: match.start()].count("\n") + 1
            violations.append(
                ContractViolation(
                    file=str_path,
                    line=line_number,
                    code=pattern.code,
                    severity=pattern.severity,
                    found=match.group().strip(),
                    suggestion=pattern.suggestion,
                    description=pattern.description,
                )
            )

    return violations


def scan_path(path: Path, patterns: list[BypassPattern] | None = None) -> list[ContractViolation]:
    """Scan a file or directory for contract violations.

    Directories are walked recursively.
    Skips ``.git``, ``__pycache__``, ``.venv``, ``node_modules``.

    Args:
        path: File or directory to scan.
        patterns: Patterns to check (default: ALL_PATTERNS).

    Returns:
        List of violations found.

    """
    if path.is_file():
        return scan_file(path, patterns)

    violations: list[ContractViolation] = []
    skip_dirs = {
        ".git",
        "__pycache__",
        ".venv",
        "node_modules",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
    }

    for entry in sorted(path.rglob("*.py")):
        # Skip excluded directories
        if any(part in skip_dirs for part in entry.parts):
            continue
        violations.extend(scan_file(entry, patterns))

    return violations


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="lab-connectors-audit",
        description="Scan for patterns that bypass lab-connectors contracts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Scan files for contract violations")
    scan.add_argument("paths", nargs="+", type=Path, help="Files or directories to scan")
    scan.add_argument(
        "--fail",
        action="store_true",
        help="Exit code 1 if any error-level violations found",
    )
    scan.add_argument("--json", action="store_true", help="Output as JSON array")
    scan.add_argument(
        "--warnings",
        action="store_true",
        help="Include warning-level violations (default: errors only)",
    )

    return parser


def _format_text(violations: list[ContractViolation], show_warnings: bool) -> str:
    """Format violations as human-readable text."""
    errors = [v for v in violations if v.severity == "error"]
    warnings = [v for v in violations if v.severity == "warning"]

    lines: list[str] = []

    if errors:
        lines.append(f"❌ {len(errors)} error(s):")
        for v in errors:
            lines.append(f"   {v.file}:{v.line}  {v.code}")
            lines.append(f"       found: {v.found}")
            lines.append(f"       {v.suggestion}")
        lines.append("")

    if warnings and show_warnings:
        lines.append(f"⚠️  {len(warnings)} warning(s):")
        for v in warnings:
            lines.append(f"   {v.file}:{v.line}  {v.code}")
            lines.append(f"       found: {v.found}")
            lines.append(f"       {v.suggestion}")
        lines.append("")

    if not violations:
        lines.append("✅ No violations found.")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Returns:
        Exit code (0 = clean, 1 = violations found with --fail).

    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "scan":
        all_violations: list[ContractViolation] = []
        for p in args.paths:
            all_violations.extend(scan_path(p))

        errors = [v for v in all_violations if v.severity == "error"]

        if args.json:
            print(json.dumps([v.to_dict() for v in all_violations], indent=2))
        else:
            print(_format_text(all_violations, show_warnings=args.warnings))

        if args.fail and errors:
            return 1
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
