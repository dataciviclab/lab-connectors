"""Tests per lab_connectors.gcs.paths — contratto path GCS.

Copre:
- Caricamento contratto (load_contract)
- Accesso bucket e pattern (get_bucket, get_pattern)
- Risoluzione pattern (resolve, with/without params)
- URL composition (gs_url, https_url)
- Convenience functions (clean_parquet, pipeline_run, catalog_manifest)
- Costanti modulo (CLEAN_BUCKET, MART_BUCKET)
- Error handling (key mancanti, parametri mancanti)
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from lab_connectors.gcs.paths import (
    CLEAN_BUCKET,
    MART_BUCKET,
    catalog_manifest,
    clean_parquet,
    get_bucket,
    get_pattern,
    gs_url,
    https_url,
    load_contract,
    pipeline_run,
    resolve,
)


class TestPathsContract(unittest.TestCase):
    """Test del contratto paths.json e del modulo paths.py."""

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
        """load_contract() deve ritornare lo stesso oggetto (cache)."""
        c1 = load_contract()
        c2 = load_contract()
        self.assertIs(c1, c2)

    def test_paths_json_is_findable(self) -> None:
        """paths.json deve esistere nel package come file."""
        self.assertTrue(self.contract_path.exists(), f"{self.contract_path} not found")

    def test_paths_json_is_valid_json(self) -> None:
        """paths.json deve essere JSON valido."""
        raw = self.contract_path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
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
        with self.assertRaises(KeyError) as ctx:
            get_bucket("nonexistent")
        self.assertIn("nonexistent", str(ctx.exception))

    def test_get_bucket_returns_str(self) -> None:
        self.assertIsInstance(get_bucket("clean"), str)

    # ── patterns ─────────────────────────────────────────────────────────────

    def test_patterns_contains_all_required(self) -> None:
        required = [
            "clean_parquet",
            "pipeline_run",
            "catalog_manifest",
            "catalog_signals",
            "catalog_inventory_latest",
            "catalog_inventory_report",
            "catalog_inventory_source_check",
        ]
        patterns = self.contract["patterns"]
        for p in required:
            with self.subTest(pattern=p):
                self.assertIn(p, patterns)

    def test_get_pattern_valid(self) -> None:
        self.assertEqual(get_pattern("catalog_manifest"), "catalog/manifest.json")

    def test_get_pattern_invalid_raises(self) -> None:
        with self.assertRaises(KeyError) as ctx:
            get_pattern("nonexistent")
        self.assertIn("nonexistent", str(ctx.exception))

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
        self.assertEqual(
            result, "catalog_inventory/catalog_inventory_report.json"
        )

    def test_resolve_catalog_inventory_source_check(self) -> None:
        result = resolve("catalog_inventory_source_check")
        self.assertEqual(
            result,
            "catalog_inventory/source-check/source_check_results.parquet",
        )

    def test_resolve_missing_param_raises(self) -> None:
        with self.assertRaises(KeyError) as ctx:
            resolve("clean_parquet")  # slug e year mancanti
        self.assertIn("clean_parquet", str(ctx.exception))

    def test_resolve_invalid_pattern_raises(self) -> None:
        with self.assertRaises(KeyError) as ctx:
            resolve("nonexistent")
        self.assertIn("nonexistent", str(ctx.exception))

    # ── gs_url ───────────────────────────────────────────────────────────────

    def test_gs_url_clean_parquet(self) -> None:
        url = gs_url("clean", "clean_parquet", slug="demo", year=2024)
        self.assertEqual(
            url,
            "gs://dataciviclab-clean/demo/2024/demo_2024_clean.parquet",
        )

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
        self.assertEqual(
            url,
            "gs://dataciviclab-mart/demo/2024/demo_2024_clean.parquet",
        )

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

    def test_gs_url_and_https_url_differ_only_protocol(self) -> None:
        gs = gs_url("clean", "clean_parquet", slug="x", year=1)
        https = https_url("clean", "clean_parquet", slug="x", year=1)
        self.assertTrue(gs.startswith("gs://"))
        self.assertTrue(https.startswith("https://storage.googleapis.com/"))
        # Entrambi devono contenere lo stesso path risolto
        resolved = resolve("clean_parquet", slug="x", year=1)
        self.assertIn(resolved, gs)
        self.assertIn(resolved, https)

    # ── Convenience functions ────────────────────────────────────────────────

    def test_clean_parquet_convenience(self) -> None:
        result = clean_parquet("test_slug", 2025)
        self.assertEqual(result, "test_slug/2025/test_slug_2025_clean.parquet")

    def test_clean_parquet_year_as_string(self) -> None:
        result = clean_parquet("test_slug", "2025")
        self.assertEqual(result, "test_slug/2025/test_slug_2025_clean.parquet")

    def test_pipeline_run_convenience(self) -> None:
        result = pipeline_run("demo", 2024)
        self.assertEqual(result, "demo/2024/pipeline_run.json")

    def test_catalog_manifest_convenience(self) -> None:
        result = catalog_manifest()
        self.assertEqual(result, "catalog/manifest.json")

    # ── Module-level constants ───────────────────────────────────────────────

    def test_clean_bucket_constant(self) -> None:
        self.assertEqual(CLEAN_BUCKET, "dataciviclab-clean")

    def test_mart_bucket_constant(self) -> None:
        self.assertEqual(MART_BUCKET, "dataciviclab-mart")

    def test_constants_match_contract(self) -> None:
        self.assertEqual(CLEAN_BUCKET, self.contract["buckets"]["clean"])
        self.assertEqual(MART_BUCKET, self.contract["buckets"]["mart"])

    # ── Wildcard year (multi-file glob) ──────────────────────────────────────

    def test_resolve_clean_parquet_wildcard_year(self) -> None:
        """Usato in push_archive.py per catalog multi-file entry."""
        result = resolve("clean_parquet", slug="demo", year="*")
        self.assertEqual(result, "demo/*/demo_*_clean.parquet")

    def test_gs_url_clean_parquet_wildcard(self) -> None:
        url = gs_url("clean", "clean_parquet", slug="demo", year="*")
        self.assertEqual(
            url,
            "gs://dataciviclab-clean/demo/*/demo_*_clean.parquet",
        )


class TestPathsJsonPackageData(unittest.TestCase):
    """Verifica che paths.json sia incluso nel pacchetto installato."""

    def test_paths_json_found_in_module_directory(self) -> None:
        """paths.json deve essere nello stesso dir del modulo paths.py."""
        paths_mod = Path(__file__).resolve().parents[1] / "lab_connectors" / "gcs"
        json_file = paths_mod / "paths.json"
        self.assertTrue(json_file.exists(), f"{json_file} not found")
        self.assertTrue(json_file.is_file(), f"{json_file} is not a file")


if __name__ == "__main__":
    unittest.main()
