"""Tests per NaN/pd.NA handling nei formatters."""

from __future__ import annotations

import pytest

from lab_connectors.formatters import fmt_eur, fmt_num, fmt_pct

pytestmark = pytest.mark.pure_unit


class TestFmtEurNaN:
    def test_nan(self) -> None:
        assert fmt_eur(float("nan")) == "—"

    def test_none(self) -> None:
        assert fmt_eur(None) == "—"

    def test_pd_na(self) -> None:
        pd = pytest.importorskip("pandas")
        assert fmt_eur(pd.NA) == "—"

    def test_valid_value(self) -> None:
        assert fmt_eur(1_500_000) == "€ 1.500.000"

    def test_zero(self) -> None:
        assert fmt_eur(0) == "€ 0"

    def test_nan_compact(self) -> None:
        assert fmt_eur(float("nan"), compact=True) == "—"


class TestFmtNumNaN:
    def test_nan(self) -> None:
        assert fmt_num(float("nan")) == "—"

    def test_none(self) -> None:
        assert fmt_num(None) == "—"

    def test_pd_na(self) -> None:
        pd = pytest.importorskip("pandas")
        assert fmt_num(pd.NA) == "—"

    def test_valid_value(self) -> None:
        assert fmt_num(8701) == "8.701"


class TestFmtPctNaN:
    def test_nan(self) -> None:
        assert fmt_pct(float("nan")) == "—"

    def test_none(self) -> None:
        assert fmt_pct(None) == "—"

    def test_pd_na(self) -> None:
        pd = pytest.importorskip("pandas")
        assert fmt_pct(pd.NA) == "—"

    def test_valid_value(self) -> None:
        assert fmt_pct(0.1234) == "+12.3%"

    def test_zero(self) -> None:
        assert fmt_pct(0) == "+0.0%"
