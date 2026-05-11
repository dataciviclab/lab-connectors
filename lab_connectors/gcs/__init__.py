"""GCS client condiviso per DataCivicLab.

Supporta modalità SDK (autenticato) e HTTP API (pubblico).
Le funzioni module-level usano un client singleton lazy.
"""

from __future__ import annotations

from lab_connectors.gcs.client import (
    check_public,
    list_objects,
    object_exists,
    upload_file,
    upload_string,
)

__all__ = [
    "check_public",
    "list_objects",
    "object_exists",
    "upload_file",
    "upload_string",
]
