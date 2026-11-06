"""Tests per lab_connectors.registry.availability — anni dichiarati e pubblicati."""

from __future__ import annotations

from pathlib import Path

import pytest

from lab_connectors.registry.availability import (
    latest_published_year,
    published_years,
    year_range,
)
from lab_connectors.registry.models import Registry

pytestmark = pytest.mark.contract


def _registry(**datasets: dict) -> Registry:
    return Registry.from_dict(
        {
            "schema_version": 1,
            "repo": "demo",
            "datasets": [
                {
                    "slug": slug,
                    "period": values.get("period", {}),
                    "location": values.get("location", {}),
                }
                for slug, values in datasets.items()
            ],
        }
    )


def _glob_probe(available: set[int]):
    calls: list[str] = []

    def probe(uri: str) -> bool:
        calls.append(uri)
        return any(f"/{year}/" in uri for year in available) or any(
            f"_{year}_" in uri for year in available
        )

    probe.calls = calls  # type: ignore[attr-defined]
    return probe


class TestYearRange:
    def test_range_completo_non_solo_estremi(self) -> None:
        reg = _registry(demo={"period": {"start": 2020, "end": 2023}})
        assert year_range(reg, slug="demo") == [2020, 2021, 2022, 2023]

    def test_union_multi_dataset_e_filtro_slug(self) -> None:
        reg = _registry(
            a={"period": {"start": 2020, "end": 2021}},
            b={"period": {"start": 2022, "end": 2023}},
        )
        assert year_range(reg) == [2020, 2021, 2022, 2023]
        assert year_range(reg, slug="b") == [2022, 2023]

    def test_filtro_locale_solo_anni_presenti(self, tmp_path: Path) -> None:
        reg = _registry(demo={"period": {"start": 2020, "end": 2022}})
        (tmp_path / "clean" / "demo" / "2020").mkdir(parents=True)
        (tmp_path / "clean" / "demo" / "2022").mkdir(parents=True)
        assert year_range(reg, slug="demo", local_root=tmp_path) == [2020, 2022]

    def test_period_assente(self) -> None:
        assert year_range(_registry(demo={})) == []


class TestPublishedYears:
    def test_path_puntuale_senza_rete(self) -> None:
        reg = _registry(
            demo={
                "period": {"start": 2020, "end": 2024},
                "location": {
                    "path": "gs://bucket/prefix/demo/2024/demo_2024_clean.parquet",
                    "multi_file": False,
                },
            }
        )
        probe = _glob_probe(set())
        assert published_years(reg, "demo", probe=probe) == [2024]
        assert probe.calls == []  # type: ignore[attr-defined]

    def test_glob_verifica_solo_gli_anni_del_period(self) -> None:
        reg = _registry(
            demo={
                "period": {"start": 2021, "end": 2023},
                "location": {
                    "path": "gs://bucket/prefix/demo/*/demo_*_clean.parquet",
                    "multi_file": True,
                },
            }
        )
        probe = _glob_probe({2022, 2023})
        assert published_years(reg, "demo", probe=probe) == [2022, 2023]
        assert len(probe.calls) == 3  # type: ignore[attr-defined]

    def test_slug_sconosciuto(self) -> None:
        assert published_years(_registry(demo={}), "altro") == []

    def test_location_non_gcs(self) -> None:
        reg = _registry(demo={"location": {"path": "local/file.parquet"}})
        assert published_years(reg, "demo") == []


class TestLatestPublishedYear:
    def test_usa_anno_da_location(self) -> None:
        reg = _registry(
            demo={
                "location": {
                    "path": "gs://bucket/prefix/demo/2025/demo_2025_clean.parquet",
                    "multi_file": False,
                }
            }
        )
        assert latest_published_year(reg, "demo") == 2025

    def test_glob_sceglie_il_max(self) -> None:
        reg = _registry(
            demo={
                "period": {"start": 2022, "end": 2024},
                "location": {
                    "path": "gs://bucket/prefix/demo/*/demo_*_clean.parquet",
                    "multi_file": True,
                },
            }
        )
        probe = _glob_probe({2023, 2024})
        assert latest_published_year(reg, "demo", probe=probe) == 2024

    def test_fallback_head_su_clean_parquet(self) -> None:
        reg = _registry(demo={"period": {"start": 2020, "end": 2021}})
        probe = _glob_probe({2025})
        # prefix dal registry assente: la funzione usa ""
        assert latest_published_year(reg, "demo", probe=probe, today_year=2026) == 2025

    def test_nessuna_pubblicazione_ritorna_none(self) -> None:
        reg = _registry(demo={})
        assert latest_published_year(reg, "demo", probe=_glob_probe(set()), today_year=2026) is None

    def test_mart_senza_table_errore(self) -> None:
        reg = _registry(demo={})
        with pytest.raises(ValueError, match="table"):
            latest_published_year(reg, "demo", layer="mart")

    def test_layer_non_supportato(self) -> None:
        reg = _registry(demo={})
        with pytest.raises(ValueError, match="layer"):
            latest_published_year(reg, "demo", layer="raw")
