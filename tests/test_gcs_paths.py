"""Tests per lab_connectors.gcs.paths — contratto path GCS.

Copre:
- Caricamento contratto (load_contract)
- Accesso bucket (get_bucket)
- Risoluzione pattern (resolve, con/senza parametri, wildcard, errori)
- URL composition (gs_url, https_url)
- Convenience functions (pipeline_run, catalog_manifest)
- Costanti (CLEAN_BUCKET, MART_BUCKET)
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from lab_connectors.gcs.paths import (
    CLEAN_BUCKET,
    MART_BUCKET,
    catalog_manifest,
    get_bucket,
    gs_url,
    https_url,
    load_contract,
    mart_parquet,
    pipeline_run,
    resolve,
)


class TestPathsContract(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = load_contract()
        self.contract_path = (
            Path(__file__).resolve().parents[1]
            / "lab_connectors"
            / "gcs"
            / "paths.json"
        )

    # ── load_contract ────────────────────────────────────────────────────────

    def test_load_contract_returns_dict(self) -> None:
        self.assertIsInstance(self.contract, dict)

    def test_load_contract_has_required_keys(self) -> None:
        for key in ("version", "buckets", "patterns"):
            self.assertIn(key, self.contract)

    def test_load_contract_version(self) -> None:
        self.assertEqual(self.contract["version"], 1)

    def test_load_contract_idempotent(self) -> None:
        c1 = load_contract()
        c2 = load_contract()
        self.assertIs(c1, c2)

    def test_paths_json_is_findable(self) -> None:
        self.assertTrue(self.contract_path.exists())

    def test_paths_json_is_valid_json(self) -> None:
        parsed = json.loads(self.contract_path.read_text(encoding="utf-8"))
        self.assertIn("buckets", parsed)

    # ── buckets ──────────────────────────────────────────────────────────────

    def test_buckets_contains_clean_and_mart(self) -> None:
        buckets = self.contract["buckets"]
        self.assertIn("clean", buckets)
        self.assertIn("mart", buckets)

    def test_get_bucket_valid(self) -> None:
        self.assertEqual(get_bucket("clean"), "dataciviclab-clean")
        self.assertEqual(get_bucket("mart"), "dataciviclab-mart")

    def test_get_bucket_invalid_raises(self) -> None:
        with self.assertRaises(KeyError):
            get_bucket("nonexistent")

    def test_get_bucket_returns_str(self) -> None:
        self.assertIsInstance(get_bucket("clean"), str)

    # ── patterns (via resolve) ───────────────────────────────────────────────

    def test_patterns_contains_all_required(self) -> None:
        required = [
            "clean_parquet",
            "pipeline_run",
            "catalog_manifest",
            "catalog_signals",
            "catalog_inventory_latest",
            "catalog_inventory_report",
            "catalog_inventory_source_check",
            "mart_parquet",
        ]
        patterns = self.contract["patterns"]
        for p in required:
            with self.subTest(pattern=p):
                self.assertIn(p, patterns)

    # ── resolve ──────────────────────────────────────────────────────────────

    def test_resolve_clean_parquet(self) -> None:
        result = resolve("clean_parquet", slug="ispra_ru_base", year=2024)
        self.assertEqual(result, "ispra_ru_base/2024/ispra_ru_base_2024_clean.parquet")

    def test_resolve_clean_parquet_year_as_str(self) -> None:
        result = resolve("clean_parquet", slug="test", year="2025")
        self.assertEqual(result, "test/2025/test_2025_clean.parquet")

    def test_resolve_pipeline_run(self) -> None:
        result = resolve("pipeline_run", slug="demo", year=2024)
        self.assertEqual(result, "demo/2024/pipeline_run.json")

    def test_resolve_catalog_manifest_no_params(self) -> None:
        result = resolve("catalog_manifest")
        self.assertEqual(result, "catalog/manifest.json")

    def test_resolve_catalog_signals_no_params(self) -> None:
        result = resolve("catalog_signals")
        self.assertEqual(result, "catalog/catalog_signals.json")

    def test_resolve_catalog_inventory_latest(self) -> None:
        result = resolve("catalog_inventory_latest")
        self.assertEqual(result, "catalog_inventory/catalog_inventory_latest.parquet")

    def test_resolve_catalog_inventory_report(self) -> None:
        result = resolve("catalog_inventory_report")
        self.assertEqual(result, "catalog_inventory/catalog_inventory_report.json")

    def test_resolve_catalog_inventory_source_check(self) -> None:
        result = resolve("catalog_inventory_source_check")
        self.assertEqual(
            result,
            "catalog_inventory/source-check/source_check_results.parquet",
        )

    def test_resolve_missing_param_raises(self) -> None:
        with self.assertRaises(KeyError) as ctx:
            resolve("clean_parquet")
        self.assertIn("clean_parquet", str(ctx.exception))

    def test_resolve_invalid_pattern_raises(self) -> None:
        with self.assertRaises(KeyError) as ctx:
            resolve("nonexistent")
        self.assertIn("nonexistent", str(ctx.exception))

    # ── Wildcard year (multi-file glob per catalog) ──────────────────────────

    def test_resolve_clean_parquet_wildcard_year(self) -> None:
        result = resolve("clean_parquet", slug="demo", year="*")
        self.assertEqual(result, "demo/*/demo_*_clean.parquet")

    def test_gs_url_clean_parquet_wildcard(self) -> None:
        url = gs_url("clean", "clean_parquet", slug="demo", year="*")
        self.assertEqual(url, "gs://dataciviclab-clean/demo/*/demo_*_clean.parquet")

    # ── gs_url ───────────────────────────────────────────────────────────────

    def test_gs_url_clean_parquet(self) -> None:
        url = gs_url("clean", "clean_parquet", slug="demo", year=2024)
        self.assertEqual(url, "gs://dataciviclab-clean/demo/2024/demo_2024_clean.parquet")

    def test_gs_url_catalog_inventory_report(self) -> None:
        url = gs_url("clean", "catalog_inventory_report")
        self.assertEqual(
            url,
            "gs://dataciviclab-clean/catalog_inventory/catalog_inventory_report.json",
        )

    def test_gs_url_catalog_inventory_source_check(self) -> None:
        url = gs_url("clean", "catalog_inventory_source_check")
        self.assertEqual(
            url,
            "gs://dataciviclab-clean/catalog_inventory/source-check/source_check_results.parquet",
        )

    def test_gs_url_mart_bucket(self) -> None:
        url = gs_url("mart", "clean_parquet", slug="demo", year=2024)
        self.assertEqual(url, "gs://dataciviclab-mart/demo/2024/demo_2024_clean.parquet")

    def test_gs_url_invalid_bucket_raises(self) -> None:
        with self.assertRaises(KeyError):
            gs_url("nonexistent", "catalog_manifest")

    # ── https_url ────────────────────────────────────────────────────────────

    def test_https_url_clean_parquet(self) -> None:
        url = https_url("clean", "clean_parquet", slug="demo", year=2024)
        self.assertEqual(
            url,
            "https://storage.googleapis.com/dataciviclab-clean/demo/2024/demo_2024_clean.parquet",
        )

    def test_https_url_catalog_inventory_latest(self) -> None:
        url = https_url("clean", "catalog_inventory_latest")
        self.assertEqual(
            url,
            "https://storage.googleapis.com/dataciviclab-clean"
            "/catalog_inventory/catalog_inventory_latest.parquet",
        )

    def test_gs_url_and_https_url_share_same_path(self) -> None:
        resolved = resolve("clean_parquet", slug="x", year=1)
        gs = gs_url("clean", "clean_parquet", slug="x", year=1)
        https = https_url("clean", "clean_parquet", slug="x", year=1)
        self.assertIn(resolved, gs)
        self.assertIn(resolved, https)

    # ── Convenience functions ────────────────────────────────────────────────

    def test_pipeline_run_convenience(self) -> None:
        result = pipeline_run("demo", 2024)
        self.assertEqual(result, "demo/2024/pipeline_run.json")

    def test_catalog_manifest_convenience(self) -> None:
        result = catalog_manifest()
        self.assertEqual(result, "catalog/manifest.json")

    def test_pipeline_run_matches_resolve(self) -> None:
        self.assertEqual(
            pipeline_run("demo", 2024),
            resolve("pipeline_run", slug="demo", year=2024),
        )

    def test_catalog_manifest_matches_resolve(self) -> None:
        self.assertEqual(
            catalog_manifest(),
            resolve("catalog_manifest"),
        )

    # ── mart_parquet ──────────────────────────────────────────────────────────

    def test_resolve_mart_parquet(self) -> None:
        result = resolve("mart_parquet", slug="ispra_ru_base", year=2024, table="costi")
        self.assertEqual(result, "ispra_ru_base/2024/costi.parquet")

    def test_resolve_mart_parquet_year_as_str(self) -> None:
        result = resolve("mart_parquet", slug="t", year="2025", table="tabella")
        self.assertEqual(result, "t/2025/tabella.parquet")

    def test_mart_parquet_convenience(self) -> None:
        result = mart_parquet("ispra_ru_base", 2024, "costi")
        self.assertEqual(result, "ispra_ru_base/2024/costi.parquet")

    def test_mart_parquet_convenience_year_str(self) -> None:
        result = mart_parquet("slug", "2025", "tabella")
        self.assertEqual(result, "slug/2025/tabella.parquet")

    def test_mart_parquet_matches_resolve(self) -> None:
        self.assertEqual(
            mart_parquet("demo", 2024, "costi"),
            resolve("mart_parquet", slug="demo", year=2024, table="costi"),
        )

    def test_gs_url_mart_parquet(self) -> None:
        url = gs_url("mart", "mart_parquet", slug="demo", year=2024, table="costi")
        self.assertEqual(
            url, "gs://dataciviclab-mart/demo/2024/costi.parquet"
        )

    def test_https_url_mart_parquet(self) -> None:
        url = https_url("mart", "mart_parquet", slug="demo", year=2024, table="costi")
        self.assertEqual(
            url,
            "https://storage.googleapis.com/dataciviclab-mart/demo/2024/costi.parquet",
        )

    # ── Module-level constants ───────────────────────────────────────────────

    def test_clean_bucket_constant(self) -> None:
        self.assertEqual(CLEAN_BUCKET, "dataciviclab-clean")

    def test_mart_bucket_constant(self) -> None:
        self.assertEqual(MART_BUCKET, "dataciviclab-mart")

    def test_constants_match_contract(self) -> None:
        self.assertEqual(CLEAN_BUCKET, self.contract["buckets"]["clean"])
        self.assertEqual(MART_BUCKET, self.contract["buckets"]["mart"])

    # ── Integration: import da package ───────────────────────────────────────

    def test_import_from_package(self) -> None:
        """Verifica che paths sia raggiungibile da lab_connectors.gcs."""
        from lab_connectors.gcs import (  # type: ignore[import-untyped]
            CLEAN_BUCKET as CB,
        )
        from lab_connectors.gcs import (
            resolve as RSLV,
        )
        self.assertEqual(CB, "dataciviclab-clean")
        self.assertEqual(RSLV("catalog_manifest"), "catalog/manifest.json")


class TestPathsJsonPackaging(unittest.TestCase):
    def test_paths_json_in_module_directory(self) -> None:
        paths_mod = Path(__file__).resolve().parents[1] / "lab_connectors" / "gcs"
        self.assertTrue((paths_mod / "paths.json").is_file())


if __name__ == "__main__":
    unittest.main()
