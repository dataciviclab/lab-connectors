"""Tests per lab_connectors.duckdb.queries — utility functions."""

from __future__ import annotations

from pathlib import Path

import pytest

from lab_connectors.duckdb.queries import detect_local_root, years_from_registry

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

    def test_multi_file_false_is_included(self) -> None:
        """Dataset con multi_file=False contribuisce agli anni (period field)."""
        reg = _FakeRegistry(
            [
                _FakeDataset(2017, 2026, multi_file=True),
                _FakeDataset(1994, 2027, multi_file=False),
            ]
        )
        assert years_from_registry(reg) == [1994, 2017, 2026, 2027]

    def test_multiple_multi_file_false(self) -> None:
        """Più dataset single-file: tutti contribuiscono."""
        reg = _FakeRegistry(
            [
                _FakeDataset(1994, 2027, multi_file=False),
                _FakeDataset(2000, 2025, multi_file=False),
            ]
        )
        assert years_from_registry(reg) == [1994, 2000, 2025, 2027]

    def test_filter_by_slug(self) -> None:
        """Filter by slug returns only years for that dataset."""
        ds1 = _FakeDataset(2020, 2026)
        ds1.slug = "ecb_cbd2"
        ds2 = _FakeDataset(1960, 2025)
        ds2.slug = "wb_financial"
        reg = _FakeRegistry([ds1, ds2])
        assert years_from_registry(reg, slug="ecb_cbd2") == [2020, 2026]
        assert years_from_registry(reg, slug="wb_financial") == [1960, 2025]

    def test_filter_by_unknown_slug(self) -> None:
        """Filter by unknown slug returns empty list."""
        ds1 = _FakeDataset(2020, 2026)
        ds1.slug = "ecb_cbd2"
        reg = _FakeRegistry([ds1])
        assert years_from_registry(reg, slug="unknown") == []


class TestDetectLocalRoot:
    """detect_local_root: auto-rilevamento out/data/."""

    def test_with_valid_repo_root(self, tmp_path: Path) -> None:
        """repo_root con out/data/ e parquet: restituisce il path."""
        data_dir = tmp_path / "out" / "data"
        data_dir.mkdir(parents=True)
        (data_dir / "test.parquet").write_bytes(b"")
        result = detect_local_root(repo_root=tmp_path)
        assert result == str(data_dir)

    def test_with_empty_out_data(self, tmp_path: Path) -> None:
        """repo_root con out/data/ vuoto: restituisce None."""
        data_dir = tmp_path / "out" / "data"
        data_dir.mkdir(parents=True)
        result = detect_local_root(repo_root=tmp_path)
        assert result is None

    def test_without_out_data(self, tmp_path: Path) -> None:
        """repo_root senza out/data/: restituisce None."""
        result = detect_local_root(repo_root=tmp_path)
        assert result is None

    def test_none_repo_root_returns_str_or_none(self) -> None:
        """Con repo_root=None, restituisce str o None (backward compat)."""
        result = detect_local_root()
        assert result is None or isinstance(result, str)
