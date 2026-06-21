"""GCS client + path contract per DataCivicLab.

Supporta modalità SDK (autenticato) e HTTP API (pubblico).
Il modulo ``paths`` espone i path contract canonici per tutti gli artifact GCS del Lab.
"""

from __future__ import annotations

from lab_connectors.gcs.client import (
    check_public,
    list_objects,
    object_exists,
    upload_file,
    upload_string,
)
from lab_connectors.gcs.manifest import read_manifest
from lab_connectors.gcs.paths import (
    CLEAN_BUCKET,
    MART_BUCKET,
    catalog_manifest,
    get_bucket,
    glob_to_regex,
    gs_url,
    https_url,
    load_contract,
    mart_parquet,
    parse_gs_url,
    pipeline_run,
    resolve,
)

__all__ = [
    # GCS client
    "check_public",
    "list_objects",
    "object_exists",
    "upload_file",
    "upload_string",
    # Path contract
    "CLEAN_BUCKET",
    "MART_BUCKET",
    "load_contract",
    "get_bucket",
    "resolve",
    "gs_url",
    "https_url",
    "parse_gs_url",
    "glob_to_regex",
    "pipeline_run",
    "catalog_manifest",
    "mart_parquet",
    # Manifest
    "read_manifest",
]
