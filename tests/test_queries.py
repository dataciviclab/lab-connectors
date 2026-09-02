"""Tests per lab_connectors.duckdb.queries — utility functions."""

from __future__ import annotations

import pytest

from lab_connectors.duckdb.queries import years_from_registry

pytestmark = pytest.mark.pure_unit


class _FakeLocation:
    """Minimal location stub for testing."""

    def __init__(self, multi_file: bool = True) -> None:
        self.multi_file = multi_file
        self.path = "gs://bucket/slug/"
        self.type = "gcs"


class _FakeDataset:
    """Minimal dataset stub for testing."""

    def __init__(
        self, start: int | None = None, end: int | None = None, multi_file: bool = True
    ) -> None:
        self.period = {}
        if start is not None:
            self.period["start"] = start
        if end is not None:
            self.period["end"] = end
        self.location = _FakeLocation(multi_file=multi_file)


class _FakeRegistry:
    """Minimal registry stub."""

    def __init__(self, datasets: list | None = None) -> None:
        self.datasets = datasets or []


class TestYearsFromRegistry:
    def test_single_dataset(self) -> None:
        reg = _FakeRegistry([_FakeDataset(2021, 2026)])
        assert years_from_registry(reg) == [2021, 2026]

    def test_multiple_datasets(self) -> None:
        reg = _FakeRegistry(
            [
                _FakeDataset(2020, 2024),
                _FakeDataset(2021, 2026),
            ]
        )
        assert years_from_registry(reg) == [2020, 2021, 2024, 2026]

    def test_empty_registry(self) -> None:
        reg = _FakeRegistry([])
        assert years_from_registry(reg) == []

    def test_dataset_with_only_start(self) -> None:
        reg = _FakeRegistry([_FakeDataset(start=2023)])
        assert years_from_registry(reg) == [2023]

    def test_dataset_with_no_period(self) -> None:
        ds = _FakeDataset()
        ds.period = {}
        reg = _FakeRegistry([ds])
        assert years_from_registry(reg) == []

    def test_multi_file_false_is_excluded(self) -> None:
        """Dataset con multi_file=False non deve contribuire agli anni."""
        reg = _FakeRegistry(
            [
                _FakeDataset(2017, 2026, multi_file=True),  # rna_aiuti_stato
                _FakeDataset(1994, 2027, multi_file=False),  # rna_misure
            ]
        )
        # Solo gli anni del dataset multi_file=True
        assert years_from_registry(reg) == [2017, 2026]

    def test_multiple_multi_file_false(self) -> None:
        """Più dataset single-file: tutti esclusi."""
        reg = _FakeRegistry(
            [
                _FakeDataset(1994, 2027, multi_file=False),
                _FakeDataset(2000, 2025, multi_file=False),
            ]
        )
        assert years_from_registry(reg) == []
