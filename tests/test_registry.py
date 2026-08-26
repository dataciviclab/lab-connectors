"""Tests per lab_connectors.registry."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lab_connectors.registry.client import (
    load_registry_local,
    registry_to_dict,
)
from lab_connectors.registry.models import (
    Column,
    Dataset,
    Location,
    Mart,
    Registry,
    Run,
    Signal,
)

pytestmark = pytest.mark.contract

SAMPLE_PATH = (
    Path(__file__).resolve().parent.parent.parent / "rna-aiuti-stato" / "registry" / "registry.json"
)


class TestModelsFromDict:
    """Parsing dataclass da dict."""

    def test_column(self) -> None:
        c = Column.from_dict({"name": "anno", "type": "INTEGER", "role": "dimension"})
        assert c.name == "anno"
        assert c.type == "INTEGER"
        assert c.semantic_type is None

    def test_location(self) -> None:
        loc = Location.from_dict(
            {"type": "gcs", "path": "gs://bucket/file.parquet", "multi_file": False}
        )
        assert loc.path == "gs://bucket/file.parquet"
        assert loc.multi_file is False

    def test_dataset_defaults(self) -> None:
        ds = Dataset.from_dict({"slug": "test"})
        assert ds.slug == "test"
        assert ds.period == {}
        assert ds.tags == []
        assert ds.columns == []

    def test_mart(self) -> None:
        m = Mart.from_dict(
            {"slug": "s__t", "dataset": "s", "table": "t", "location": {"path": "x"}}
        )
        assert m.table == "t"
        assert m.location.path == "x"

    def test_run(self) -> None:
        r = Run.from_dict(
            {"run_id": "abc", "year": 2024, "status": "SUCCESS", "duration_seconds": 1.5}
        )
        assert r.run_id == "abc"
        assert r.duration_seconds == 1.5

    def test_run_none_fields(self) -> None:
        r = Run.from_dict({})
        assert r.run_id == ""
        assert r.year is None

    def test_signal_without_run(self) -> None:
        s = Signal.from_dict({"id": "test", "status": "ok"})
        assert s.run is None

    def test_signal_with_run(self) -> None:
        s = Signal.from_dict({"id": "test", "run": {"run_id": "x", "status": "SUCCESS"}})
        assert s.run is not None
        assert s.run.run_id == "x"


class TestRegistryFromDict:
    """Parsing Registry completo."""

    @pytest.mark.skipif(not SAMPLE_PATH.exists(), reason="Sample registry non trovato")
    def test_load_rna_registry(self) -> None:
        data = json.loads(SAMPLE_PATH.read_text())
        reg = Registry.from_dict(data)
        assert reg.repo == "rna-aiuti-stato"
        assert len(reg.datasets) == 2
        assert len(reg.marts) == 10
        assert len(reg.signals) == 2
        assert reg.datasets[0].slug == "rna_aiuti_stato"
        assert reg.datasets[0].period["start"] == 2017


class TestClientLocal:
    """Load da path locale."""

    @pytest.mark.skipif(not SAMPLE_PATH.exists(), reason="Sample registry non trovato")
    def test_load_local(self) -> None:
        reg = load_registry_local(SAMPLE_PATH)
        assert reg.repo == "rna-aiuti-stato"

    def test_load_local_missing(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_registry_local("/nonexistent/registry.json")


class TestRegistryToDict:
    """Compat: Registry → dict."""

    @pytest.mark.skipif(not SAMPLE_PATH.exists(), reason="Sample registry non trovato")
    def test_to_dict(self) -> None:
        reg = load_registry_local(SAMPLE_PATH)
        d = registry_to_dict(reg)
        assert isinstance(d, dict)
        assert d["repo"] == "rna-aiuti-stato"
        assert isinstance(d["datasets"], list)
        assert isinstance(d["signals"], list)
