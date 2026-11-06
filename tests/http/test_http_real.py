"""Smoke test: HttpClient contro un endpoint reale del Lab.

Questo test fa una chiamata HTTP GET reale a un artifact pubblico del Lab
(``catalog_inventory/catalog_inventory_report.json``, prodotto da SO) per
verificare che ``HttpClient`` funzioni end-to-end con la rete reale —
DNS, TLS, response parsing, timeout.

Nota: il target è volutamente un artifact **vivo e piccolo**. Il
``gcs_manifest.json`` è in dismissione (sostituito dai ``registry.json`` dei
repo) e ``catalog/manifest.json`` è fermo dal 2026-08-05: nessuno dei due è
un buon candidato per uno smoke test.

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

SMOKE_URL = (
    "https://storage.googleapis.com/dataciviclab-clean/"
    "catalog_inventory/catalog_inventory_report.json"
)


@pytest.mark.smoke
def test_get_catalog_inventory_report() -> None:
    """GET catalog_inventory_report.json → 200 + JSON con 'sources'."""
    _require_smoke_env()

    client = HttpClient(timeout=20, max_retries=1)
    result = client.get(SMOKE_URL)

    _assert_result_ok(result)
    assert result.response is not None
    data = result.response.json()
    assert isinstance(data, dict)
    assert "sources" in data, "il report deve contenere 'sources'"
    assert isinstance(data["sources"], dict)
    assert data["sources"], "il report non deve essere vuoto"
    assert isinstance(data.get("captured_at"), str)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _require_smoke_env() -> None:
    """Skip test unless ``SMOKE_TESTS=1`` is set.

    Previene esecuzione accidentale in PR CI.
    """
    if not os.environ.get("SMOKE_TESTS"):
        pytest.skip("SMOKE_TESTS not set — smoke test skipped. Set SMOKE_TESTS=1 to enable.")


def _assert_result_ok(result: HttpResult) -> None:
    """Assert the result is usable (network + HTTP success)."""
    assert result.is_ok, (
        f"HTTP request failed: {result.err}. SSL fallback: {result.ssl_fallback_used}"
    )
    assert result.response is not None
    assert result.response.status_code == 200
