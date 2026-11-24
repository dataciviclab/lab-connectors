"""Tests registry schema v2 (contratto gcs + partitions + last_run).

v2 non scrive più ``location`` voce per voce né la sezione ``signals``:
il file dichiara il contratto di pubblicazione (``gcs``), le partizioni
pubblicate con le righe clean (``partitions``) e l'ultima esecuzione
(``last_run``). ``Registry.from_dict`` sintetizza le ``location``, così i
consumer tipizzati non cambiano.
"""

from __future__ import annotations

import pytest

from lab_connectors.registry.availability import latest_published_year, published_years
from lab_connectors.registry.locations import clean_location, mart_location
from lab_connectors.registry.models import Mart, Registry

pytestmark = pytest.mark.contract

CLEAN = "gs://dataciviclab-clean"
MART = "gs://dataciviclab-mart"


def _registry(**overrides) -> dict:
    base = {
        "schema_version": 2,
        "repo": "demo",
        "source_repo": "dataciviclab/demo",
        "updated_at": "2026-11-24",
        "gcs": {"prefix": "demo/", "clean": "year"},
        "datasets": [],
        "marts": [],
    }
    base.update(overrides)
    return base


class TestPartitions:
    def test_years_and_clean_rows(self) -> None:
        reg = Registry.from_dict(
            _registry(datasets=[{"slug": "ds", "partitions": {"2023": 10, "2024": 25}}])
        )
        ds = reg.datasets[0]
        assert ds.years == [2023, 2024]
        assert ds.clean_rows == 35

    def test_no_partitions(self) -> None:
        reg = Registry.from_dict(_registry(datasets=[{"slug": "ds"}]))
        assert reg.datasets[0].years == []
        assert reg.datasets[0].clean_rows is None

    def test_non_numeric_keys_ignored(self) -> None:
        reg = Registry.from_dict(_registry(datasets=[{"slug": "ds", "partitions": {"x": 1}}]))
        assert reg.datasets[0].partitions == {}


class TestLastRun:
    def test_parsed_into_run(self) -> None:
        reg = Registry.from_dict(
            _registry(
                datasets=[
                    {
                        "slug": "ds",
                        "last_run": {
                            "at": "2026-11-17T17:01:24Z",
                            "year": 2017,
                            "status": "SUCCESS",
                        },
                    }
                ]
            )
        )
        run = reg.datasets[0].last_run
        assert run is not None
        assert run.started_at == "2026-11-17T17:01:24Z"
        assert run.year == 2017
        assert run.status == "SUCCESS"

    def test_absent(self) -> None:
        reg = Registry.from_dict(_registry(datasets=[{"slug": "ds"}]))
        assert reg.datasets[0].last_run is None


class TestDerivedLocations:
    def test_clean_single_year(self) -> None:
        reg = Registry.from_dict(_registry(datasets=[{"slug": "ds", "partitions": {"2024": 1}}]))
        assert reg.datasets[0].location.path == f"{CLEAN}/demo/ds/2024/ds_2024_clean.parquet"
        assert reg.datasets[0].location.multi_file is False

    def test_clean_multi_year_glob(self) -> None:
        reg = Registry.from_dict(
            _registry(datasets=[{"slug": "ds", "partitions": {"2023": 1, "2024": 2}}])
        )
        loc = reg.datasets[0].location
        assert loc.path == f"{CLEAN}/demo/ds/*/ds_*_clean.parquet"
        assert loc.multi_file is True

    def test_clean_flat(self) -> None:
        reg = Registry.from_dict(
            _registry(
                gcs={"prefix": "demo/", "clean": "flat"},
                datasets=[{"slug": "ds", "partitions": {"2024": 1}}],
            )
        )
        assert reg.datasets[0].location.path == f"{CLEAN}/demo/ds/ds_2024_clean.parquet"

    def test_clean_flat_multi_year_glob(self) -> None:
        loc = clean_location("demo/", "flat", "ds", {"2023": 1, "2024": 2})
        assert loc is not None
        assert loc["path"] == f"{CLEAN}/demo/ds/ds_*_clean.parquet"

    def test_mart_only_dataset_has_no_clean(self) -> None:
        reg = Registry.from_dict(_registry(datasets=[{"slug": "ds", "mart_refs": ["ds__m"]}]))
        assert reg.datasets[0].location.path == ""

    def test_explicit_location_override(self) -> None:
        reg = Registry.from_dict(
            _registry(
                datasets=[
                    {
                        "slug": "ds",
                        "partitions": {"2024": 1},
                        "location": f"{CLEAN}/custom/x.parquet",
                    }
                ]
            )
        )
        assert reg.datasets[0].location.path == f"{CLEAN}/custom/x.parquet"

    def test_mart_flat(self) -> None:
        reg = Registry.from_dict(
            _registry(marts=[{"slug": "ds__m", "dataset": "ds", "table": "m"}])
        )
        assert reg.marts[0].location.path == f"{MART}/demo/ds/m.parquet"

    def test_mart_year(self) -> None:
        reg = Registry.from_dict(
            _registry(
                marts=[
                    {"slug": "ds__m", "dataset": "ds", "table": "m", "layout": "year", "year": 2024}
                ]
            )
        )
        assert reg.marts[0].location.path == f"{MART}/demo/ds/2024/m.parquet"

    def test_mart_glob(self) -> None:
        reg = Registry.from_dict(
            _registry(marts=[{"slug": "ds__m", "dataset": "ds", "table": "m", "layout": "glob"}])
        )
        assert reg.marts[0].location.path == f"{MART}/demo/ds/*/m.parquet"
        assert reg.marts[0].location.multi_file is True

    def test_mart_year_without_year_raises(self) -> None:
        with pytest.raises(ValueError, match="richiede l'anno"):
            mart_location("demo/", "ds", "m", "year")

    def test_mart_primary_key(self) -> None:
        mart = Mart.from_dict(
            {"slug": "ds__m", "dataset": "ds", "table": "m", "primary_key": ["a"]}
        )
        assert mart.primary_key == ["a"]


class TestPrefix:
    def test_prefix_from_gcs_block(self) -> None:
        reg = Registry.from_dict(_registry(datasets=[{"slug": "ds", "partitions": {"2024": 1}}]))
        assert reg.prefix_for_slug("ds") == "demo/"
        assert reg.prefix_for_slug("altro") == "demo/"

    def test_prefix_normalized(self) -> None:
        loc = clean_location("demo", "year", "ds", {"2024": 1})
        assert loc is not None
        assert loc["path"] == f"{CLEAN}/demo/ds/2024/ds_2024_clean.parquet"


class TestAvailabilityV2:
    def test_published_years_no_probe(self) -> None:
        reg = Registry.from_dict(
            _registry(datasets=[{"slug": "ds", "partitions": {"2023": 1, "2024": 2}}])
        )

        def boom(uri: str) -> bool:
            raise AssertionError(f"probe chiamato per {uri}")

        assert published_years(reg, "ds", probe=boom) == [2023, 2024]

    def test_latest_published_year_no_probe(self) -> None:
        reg = Registry.from_dict(_registry(datasets=[{"slug": "ds", "partitions": {"2024": 7}}]))
        assert latest_published_year(reg, "ds", probe=lambda _u: False) == 2024


class TestV1StillWorks:
    def test_v1_location_untouched(self) -> None:
        reg = Registry.from_dict(
            {
                "schema_version": 1,
                "datasets": [
                    {
                        "slug": "ds",
                        "location": {
                            "type": "gcs",
                            "path": f"{CLEAN}/p/ds/2024/ds_2024_clean.parquet",
                            "multi_file": False,
                        },
                    }
                ],
                "signals": [{"id": "ds", "status": "ok"}],
            }
        )
        assert reg.schema_version == 1
        assert reg.datasets[0].location.path.endswith("ds/2024/ds_2024_clean.parquet")
        assert reg.datasets[0].partitions == {}
        assert len(reg.signals) == 1
        assert reg.prefix_for_slug("ds") == "p/"
