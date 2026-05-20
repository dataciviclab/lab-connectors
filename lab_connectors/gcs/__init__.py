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
    "get_pattern",
    "resolve",
    "gs_url",
    "https_url",
    "clean_parquet",
    "pipeline_run",
    "catalog_manifest",
]
