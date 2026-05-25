"""Smoke test: HttpClient contro un endpoint reale del Lab.

Questo test fa una chiamata HTTP GET reale al manifest del catalogo
su GCS pubblico per verificare che ``HttpClient`` funzioni end-to-end
con la rete reale — DNS, TLS, response parsing, timeout.

Il test è **skippato di default** (usa ``SMOKE_TESTS=1`` per abilitarlo)
ed è pensato per essere eseguito su schedule (settimanale) o on-demand.
Cattura cambiamenti upstream che i test mock-based non vedono:
- Certificati TLS scaduti o revocati
- Cambiamenti al contratto dell'endpoint
- Downtime dell'infrastruttura GCS/catalogo
"""
from __future__ import annotations

import os

import pytest

from lab_connectors.http import HttpClient
from lab_connectors.http.types import HttpResult

MANIFEST_URL = (
    "https://storage.googleapis.com/dataciviclab-clean/catalog/manifest.json"
)


@pytest.mark.smoke
def test_get_catalog_manifest() -> None:
    """GET catalog/manifest.json → 200 + JSON con 'items' e 'generated_at'."""
    _require_smoke_env()

    client = HttpClient(timeout=15, max_retries=1)
    result = client.get(MANIFEST_URL)

    _assert_result_ok(result)
    assert result.response is not None
    data = result.response.json()
    assert isinstance(data, dict)
    assert "items" in data, "manifest.json deve contenere 'items'"
    assert "generated_at" in data, "manifest.json deve contenere 'generated_at'"
    assert isinstance(data["items"], list)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _require_smoke_env() -> None:
    """Skip test unless ``SMOKE_TESTS=1`` is set.

    Previene esecuzione accidentale in PR CI.
    """
    if not os.environ.get("SMOKE_TESTS"):
        pytest.skip(
            "SMOKE_TESTS not set — smoke test skipped. "
            "Set SMOKE_TESTS=1 to enable."
        )


def _assert_result_ok(result: HttpResult) -> None:
    """Assert the result is usable (network + HTTP success)."""
    assert result.is_ok, (
        f"HTTP request failed: {result.err}. "
        f"SSL fallback: {result.ssl_fallback_used}"
    )
    assert result.response is not None
    assert result.response.status_code == 200
