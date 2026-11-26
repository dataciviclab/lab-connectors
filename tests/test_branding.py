"""Test per lab_connectors.branding e per gli asset di brand spediti col pacchetto."""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from importlib import resources
from unittest.mock import MagicMock, patch

import pytest


def _brand_dir():
    return resources.files("lab_connectors").joinpath("assets", "brand")


@pytest.mark.pure_unit
def test_asset_spediti_e_svg_validi():
    """I tre asset di brand sono nel pacchetto e sono SVG validi."""
    for name in ("symbol.svg", "symbol-on-dark.svg", "favicon.svg"):
        path = _brand_dir().joinpath(name)
        assert path.is_file(), f"{name} mancante nel pacchetto"
        root = ET.fromstring(path.read_text())
        assert root.tag.endswith("svg")


@pytest.mark.pure_unit
def test_asset_coerenti_col_manifest():
    """Il contenuto degli asset corrisponde agli hash dichiarati."""
    manifest = json.loads(_brand_dir().joinpath("MANIFEST.json").read_text())
    for name, meta in manifest["files"].items():
        digest = hashlib.sha256(_brand_dir().joinpath(name).read_bytes()).hexdigest()
        assert digest == meta["sha256"], f"{name} diverge dal manifest: risincronizzare da lab-ops"


@pytest.mark.pure_unit
def test_manifest_dichiara_la_fonte_canonica():
    """Il manifest dice da dove vengono gli asset, così la copia non diventa una fonte."""
    manifest = json.loads(_brand_dir().joinpath("MANIFEST.json").read_text())
    assert manifest["canonical"].endswith("lab-ops/standards/assets/logo")
    assert "non modificare qui" in manifest["note"]


@pytest.mark.pure_unit
def test_apply_branding_usa_asset_locali():
    """apply_branding() passa a st.logo un file del pacchetto, non un URL."""
    mock_st = MagicMock()

    with patch.dict("sys.modules", {"streamlit": mock_st}):
        from lab_connectors.branding import apply_branding

        apply_branding()

        image = mock_st.logo.call_args[0][0]
        assert image.endswith(".svg")
        assert "raw.githubusercontent" not in image
        assert "/assets/brand/" in image.replace("\\", "/")


@pytest.mark.pure_unit
@pytest.mark.parametrize(
    ("variant", "expected"),
    [("light", "symbol.svg"), ("dark", "symbol-on-dark.svg")],
)
def test_variante_forzata(variant, expected):
    """La variante forzata sceglie il file giusto."""
    mock_st = MagicMock()

    with patch.dict("sys.modules", {"streamlit": mock_st}):
        from lab_connectors.branding import apply_branding

        apply_branding(variant=variant)

        assert mock_st.logo.call_args[0][0].endswith(expected)


@pytest.mark.pure_unit
def test_variante_auto_segue_il_tema():
    """Con variant='auto' il marchio segue il tema dichiarato da Streamlit."""
    mock_st = MagicMock()
    mock_st.context.theme.type = "dark"

    with patch.dict("sys.modules", {"streamlit": mock_st}):
        from lab_connectors.branding import apply_branding

        apply_branding()

        assert mock_st.logo.call_args[0][0].endswith("symbol-on-dark.svg")


@pytest.mark.pure_unit
def test_variante_auto_senza_tema_usa_chiaro():
    """Se Streamlit non espone il tema, il default è chiaro (default di Streamlit)."""
    mock_st = MagicMock()
    mock_st.context.theme.type = None

    with patch.dict("sys.modules", {"streamlit": mock_st}):
        from lab_connectors.branding import apply_branding

        apply_branding()

        assert mock_st.logo.call_args[0][0].endswith("symbol.svg")


@pytest.mark.pure_unit
def test_apply_branding_with_repo():
    """apply_branding() con repo_name/repo_url mostra il link nel sidebar."""
    mock_st = MagicMock()

    with patch.dict("sys.modules", {"streamlit": mock_st}):
        from lab_connectors.branding import apply_branding

        apply_branding(repo_name="mio-repo", repo_url="https://github.com/test")

        caption_call = mock_st.sidebar.caption.call_args[0][0]
        assert "mio-repo" in caption_call
        assert "https://github.com/test" in caption_call
        assert "CC BY 4.0" in caption_call


@pytest.mark.pure_unit
def test_apply_branding_without_repo():
    """apply_branding() senza repo mostra solo DataCivicLab."""
    mock_st = MagicMock()

    with patch.dict("sys.modules", {"streamlit": mock_st}):
        from lab_connectors.branding import apply_branding

        apply_branding()

        caption_call = mock_st.sidebar.caption.call_args[0][0]
        assert "DataCivicLab" in caption_call
        assert "CC BY 4.0" in caption_call
        assert "mio-repo" not in caption_call


@pytest.mark.pure_unit
def test_licenza_omessa_se_none():
    """license_name=None toglie l'attribuzione di licenza, per repo con licenza diversa."""
    mock_st = MagicMock()

    with patch.dict("sys.modules", {"streamlit": mock_st}):
        from lab_connectors.branding import apply_branding

        apply_branding(license_name=None)

        caption_call = mock_st.sidebar.caption.call_args[0][0]
        assert "CC BY 4.0" not in caption_call


@pytest.mark.pure_unit
def test_apply_branding_custom_size():
    """apply_branding() passa la size a st.logo()."""
    mock_st = MagicMock()

    with patch.dict("sys.modules", {"streamlit": mock_st}):
        from lab_connectors.branding import apply_branding

        apply_branding(size="small")

        assert mock_st.logo.call_args[1]["size"] == "small"
