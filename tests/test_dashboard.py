"""Tests per lab_connectors.dashboard."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.pure_unit
def test_dashboard_config_defaults():
    """DashboardConfig ha defaults sensati."""
    from lab_connectors.dashboard import DashboardConfig

    cfg = DashboardConfig(title="Test Dashboard")
    assert cfg.title == "Test Dashboard"
    assert cfg.icon == "📊"
    assert cfg.layout == "wide"
    assert cfg.sidebar_state == "expanded"
    assert cfg.repo_name == ""
    assert cfg.repo_url == ""
    assert cfg.sources_text == ""


@pytest.mark.pure_unit
def test_dashboard_config_custom():
    """DashboardConfig accetta parametri custom."""
    from lab_connectors.dashboard import DashboardConfig

    cfg = DashboardConfig(
        title="Custom",
        icon="🚀",
        repo_name="mio-repo",
        repo_url="https://github.com/test",
        sources_text="Fonti: MEF",
        layout="centered",
    )
    assert cfg.title == "Custom"
    assert cfg.icon == "🚀"
    assert cfg.repo_name == "mio-repo"
    assert cfg.sources_text == "Fonti: MEF"
    assert cfg.layout == "centered"


@pytest.mark.pure_unit
def test_run_dashboard_calls_st_config():
    """run_dashboard() chiama st.set_page_config con i parametri corretti."""
    from lab_connectors.dashboard import DashboardConfig, run_dashboard

    mock_st = MagicMock()
    mock_pages = {"": [MagicMock()]}

    with patch.dict("sys.modules", {"streamlit": mock_st}):
        config = DashboardConfig(title="Test", icon="🚀", layout="centered")
        run_dashboard(config, mock_pages)

        mock_st.set_page_config.assert_called_once_with(
            page_title="Test",
            page_icon="🚀",
            layout="centered",
            initial_sidebar_state="expanded",
        )


@pytest.mark.pure_unit
def test_run_dashboard_calls_navigation():
    """run_dashboard() chiama st.navigation + pg.run()."""
    from lab_connectors.dashboard import DashboardConfig, run_dashboard

    mock_st = MagicMock()
    mock_pg = MagicMock()
    mock_st.navigation.return_value = mock_pg
    mock_pages = {"": [MagicMock()]}

    with patch.dict("sys.modules", {"streamlit": mock_st}):
        config = DashboardConfig(title="Test")
        run_dashboard(config, mock_pages)

        mock_st.navigation.assert_called_once_with(mock_pages, position="sidebar")
        mock_pg.run.assert_called_once()


@pytest.mark.pure_unit
def test_run_dashboard_sources_text():
    """run_dashboard() renderizza sources_text nel sidebar."""
    from lab_connectors.dashboard import DashboardConfig, run_dashboard

    mock_st = MagicMock()
    mock_pages = {"": [MagicMock()]}

    with patch.dict("sys.modules", {"streamlit": mock_st}):
        config = DashboardConfig(title="Test", sources_text="Fonti: MEF")
        run_dashboard(config, mock_pages)

        # Find the caption call with "Fonti: MEF"
        caption_calls = [call[0][0] for call in mock_st.sidebar.caption.call_args_list]
        assert any("Fonti: MEF" in c for c in caption_calls)


@pytest.mark.pure_unit
def test_run_dashboard_no_sources_text():
    """run_dashboard() senza sources_text non aggiunge caption extra."""
    from lab_connectors.dashboard import DashboardConfig, run_dashboard

    mock_st = MagicMock()
    mock_pages = {"": [MagicMock()]}

    with patch.dict("sys.modules", {"streamlit": mock_st}):
        config = DashboardConfig(title="Test")
        run_dashboard(config, mock_pages)

        caption_calls = [call[0][0] for call in mock_st.sidebar.caption.call_args_list]
        assert not any("Fonti:" in c for c in caption_calls)


@pytest.mark.pure_unit
def test_require_data_with_empty_df():
    """require_data() chiama st.warning + st.stop su DataFrame vuoto."""
    import pandas as pd

    from lab_connectors.dashboard import require_data

    mock_st = MagicMock()

    with patch.dict("sys.modules", {"streamlit": mock_st}):
        require_data(pd.DataFrame())

        mock_st.warning.assert_called_once()
        mock_st.stop.assert_called_once()


@pytest.mark.pure_unit
def test_require_data_with_none():
    """require_data(None) chiama st.warning + st.stop."""
    from lab_connectors.dashboard import require_data

    mock_st = MagicMock()

    with patch.dict("sys.modules", {"streamlit": mock_st}):
        require_data(None)

        mock_st.warning.assert_called_once()
        mock_st.stop.assert_called_once()


@pytest.mark.pure_unit
def test_require_data_with_data():
    """require_data() non fa nulla se il DataFrame ha righe."""
    import pandas as pd

    from lab_connectors.dashboard import require_data

    mock_st = MagicMock()

    with patch.dict("sys.modules", {"streamlit": mock_st}):
        require_data(pd.DataFrame({"a": [1, 2, 3]}))

        mock_st.warning.assert_not_called()
        mock_st.stop.assert_not_called()


@pytest.mark.pure_unit
def test_require_data_custom_message():
    """require_data() usa il messaggio custom."""
    import pandas as pd

    from lab_connectors.dashboard import require_data

    mock_st = MagicMock()

    with patch.dict("sys.modules", {"streamlit": mock_st}):
        require_data(pd.DataFrame(), message="Nessun dato per i filtri.")

        warning_msg = mock_st.warning.call_args[0][0]
        assert "filtri" in warning_msg


@pytest.mark.pure_unit
def test_years_for_slug():
    """years_for_slug() estrae anni dal registry per uno slug."""
    from lab_connectors.dashboard.sources import years_for_slug
    from lab_connectors.registry.models import Dataset, Registry

    registry = Registry(
        datasets=[
            Dataset(slug="ds1", period={"start": 2020, "end": 2023}),
            Dataset(slug="ds2", period={"start": 2021, "end": 2022}),
        ]
    )

    assert years_for_slug(registry, "ds1") == [2020, 2021, 2022, 2023]
    assert years_for_slug(registry, "ds2") == [2021, 2022]
    assert years_for_slug(registry, "nonexistent") == []


@pytest.mark.pure_unit
def test_years_for_slug_no_period():
    """years_for_slug() restituisce [] se il dataset non ha period."""
    from lab_connectors.dashboard.sources import years_for_slug
    from lab_connectors.registry.models import Dataset, Registry

    registry = Registry(datasets=[Dataset(slug="ds1", period={})])
    assert years_for_slug(registry, "ds1") == []


@pytest.mark.pure_unit
def test_cached_sources_init():
    """CachedSources inizializza correttamente."""
    from lab_connectors.dashboard.sources import CachedSources

    cs = CachedSources(prefix="test/", slugs=["s1", "s2"], default_year=2025, ttl=1800)
    assert cs.prefix == "test/"
    assert cs.slugs == ["s1", "s2"]
    assert cs.default_year == 2025
    assert cs.ttl == 1800
