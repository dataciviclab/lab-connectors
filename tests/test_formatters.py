"""Tests per lab_connectors.formatters."""

from __future__ import annotations

import pytest

from lab_connectors.formatters import fmt_eur, fmt_num, fmt_pct

pytestmark = pytest.mark.pure_unit


class TestFmtEur:
    def test_basic(self) -> None:
        assert fmt_eur(1_500_000) == "€ 1.500.000"

    def test_none(self) -> None:
        assert fmt_eur(None) == "—"

    def test_zero(self) -> None:
        assert fmt_eur(0) == "€ 0"

    def test_compact_mld(self) -> None:
        assert fmt_eur(2_500_000_000, compact=True) == "€ 2,5 mld"

    def test_compact_mln(self) -> None:
        assert fmt_eur(350_000_000, compact=True) == "€ 350 mln"

    def test_compact_small(self) -> None:
        assert fmt_eur(50_000, compact=True) == "€ 50.000"

    def test_negative(self) -> None:
        assert "-3.000" in fmt_eur(-3_000)


class TestFmtNum:
    def test_basic(self) -> None:
        assert fmt_num(8701) == "8.701"

    def test_none(self) -> None:
        assert fmt_num(None) == "—"

    def test_large(self) -> None:
        assert fmt_num(1_234_567) == "1.234.567"


class TestFmtPct:
    def test_positive(self) -> None:
        assert fmt_pct(0.1234) == "+12.3%"

    def test_negative(self) -> None:
        result = fmt_pct(-0.05)
        assert "5.0%" in result
        assert "−" in result or "-" in result

    def test_none(self) -> None:
        assert fmt_pct(None) == "—"

    def test_zero(self) -> None:
        assert fmt_pct(0) == "+0.0%"

    def test_custom_decimals(self) -> None:
        assert fmt_pct(0.12345, decimals=2) == "+12.35%"
