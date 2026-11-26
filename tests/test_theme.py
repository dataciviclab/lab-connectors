"""Test per lab_connectors.theme: gli accenti vengono dallo standard di brand."""

from __future__ import annotations

import pytest

from lab_connectors.theme import (
    ACCENT_DARK,
    ACCENT_LIGHT,
    BACKGROUND_DARK,
    streamlit_config,
    streamlit_theme,
)


@pytest.mark.pure_unit
def test_accenti_sono_quelli_dello_standard():
    """Gli accenti corrispondono a brand.md, non a valori scelti a caso."""
    assert ACCENT_LIGHT == "#2563EB"
    assert ACCENT_DARK == "#60A5FA"
    assert BACKGROUND_DARK == "#0E1117"


@pytest.mark.pure_unit
def test_tema_scuro_usa_l_accento_chiaro():
    """Su fondo scuro il primary è l'accento leggibile, non quello del sito chiaro."""
    theme = streamlit_theme("dark")
    assert theme["primaryColor"] == ACCENT_DARK
    assert theme["base"] == "dark"


@pytest.mark.pure_unit
def test_tema_chiaro_usa_l_accento_scuro():
    """Su fondo chiaro vale il contrario."""
    theme = streamlit_theme("light")
    assert theme["primaryColor"] == ACCENT_LIGHT
    assert theme["base"] == "light"


@pytest.mark.pure_unit
def test_config_toml_e_valido():
    """Il TOML generato è leggibile e contiene il blocco [theme]."""
    import tomllib

    parsed = tomllib.loads(streamlit_config("dark"))
    assert parsed["theme"]["primaryColor"] == ACCENT_DARK
    assert parsed["server"]["headless"] is True


@pytest.mark.pure_unit
def test_config_senza_server():
    """server_headless=False omette il blocco [server]."""
    assert "[server]" not in streamlit_config("dark", server_headless=False)
