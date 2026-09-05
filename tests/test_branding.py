"""Test per lab_connectors.branding."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.pure_unit
def test_apply_branding_calls_st_logo():
    """apply_branding() chiama st.logo() con i parametri corretti."""
    mock_st = MagicMock()

    with patch.dict("sys.modules", {"streamlit": mock_st}):
        from lab_connectors.branding import _ICON_URL, _LOGO_URL, apply_branding

        apply_branding()

        mock_st.logo.assert_called_once_with(
            _LOGO_URL,
            size="large",
            icon_image=_ICON_URL,
            link="https://dataciviclab.org",
        )


@pytest.mark.pure_unit
def test_apply_branding_with_repo():
    """apply_branding() con repo_name/repo_url mostra il link nel sidebar."""
    mock_st = MagicMock()

    with patch.dict("sys.modules", {"streamlit": mock_st}):
        from lab_connectors.branding import apply_branding

        apply_branding(repo_name="mio-repo", repo_url="https://github.com/test")

        # sidebar.caption deve contenere il nome del repo
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
def test_apply_branding_custom_size():
    """apply_branding() passa la size a st.logo()."""
    mock_st = MagicMock()

    with patch.dict("sys.modules", {"streamlit": mock_st}):
        from lab_connectors.branding import apply_branding

        apply_branding(size="small")

        call_kwargs = mock_st.logo.call_args[1]
        assert call_kwargs["size"] == "small"
