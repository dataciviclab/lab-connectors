"""Tests per lab_connectors.duckdb.queries — utility functions."""

from __future__ import annotations

from lab_connectors.duckdb.queries import years_from_registry


class _FakeDataset:
    """Minimal dataset stub for testing."""

    def __init__(self, start: int | None = None, end: int | None = None) -> None:
        self.period = {}
        if start is not None:
            self.period["start"] = start
        if end is not None:
            self.period["end"] = end


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
