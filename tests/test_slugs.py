"""Tests per lab_connectors.registry.slugs — mapping slug interno -> URL."""

from __future__ import annotations

import pytest

from lab_connectors.registry.slugs import URL_SLUG_OVERRIDES, to_url_slug

pytestmark = pytest.mark.contract


class TestToUrlSlug:
    """Contratto dello slug pubblico usato dall'Explorer."""

    def test_meccanico_senza_override(self) -> None:
        assert to_url_slug("aci_prime_iscrizioni_autovetture") == (
            "aci-prime-iscrizioni-autovetture"
        )

    def test_override_editoriale(self) -> None:
        assert to_url_slug("ispra_ru_base") == "rifiuti-urbani"
        assert to_url_slug("aifa_spesa_consumo") == "spesa-farmaceutica"

    def test_override_critici_per_i_link_dashboard(self) -> None:
        """Slug dove la conversione meccanica produrrebbe un link 404."""
        assert to_url_slug("istat_housing_crowding") == "housing-crowding"
        assert to_url_slug("mit_incidentalita_mensile") == "mit-incidentalita"
        assert to_url_slug("popolazione_istat_comunale_2019_2025") == "popolazione-istat"

    def test_slug_senza_underscore_invariato(self) -> None:
        assert to_url_slug("runts") == "runts"

    def test_tabella_override_coerente(self) -> None:
        """Ogni override è una stringa non vuota con soli caratteri URL-safe."""
        for source, target in URL_SLUG_OVERRIDES.items():
            assert source and target
            assert "_" not in target
            assert target == target.strip()
            assert to_url_slug(source) == target

    def test_idempotente_su_slug_gia_url(self) -> None:
        assert to_url_slug("rifiuti-urbani") == "rifiuti-urbani"
