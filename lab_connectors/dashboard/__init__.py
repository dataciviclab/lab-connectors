"""Componenti condivisi per dashboard Streamlit del DataCivicLab.

Centralizza il boilerplate ricorrente: ``set_page_config``, branding,
navigation, empty state guard, e cached data loaders.

Usage::

    from lab_connectors.dashboard import DashboardConfig, run_dashboard, require_data

    config = DashboardConfig(
        title="Il Mio Dataset · Dashboard",
        icon="📊",
        repo_name="mio-repo",
        repo_url="https://github.com/dataciviclab/mio-repo",
    )

    pages = {
        "": [st.Page("pages/01_Panoramica.py", title="Panoramica", icon="📊", default=True)],
    }

    run_dashboard(config, pages)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DashboardConfig:
    """Configurazione per una dashboard Streamlit."""

    title: str
    """Titolo della pagina (appare nel browser tab)."""

    icon: str = "📊"
    """Icona della pagina (emoji)."""

    repo_name: str = ""
    """Nome del repo GitHub (es. "rna-aiuti-stato")."""

    repo_url: str = ""
    """URL del repo GitHub."""

    sources_text: str = ""
    """Testo opzionale per la riga 'Fonti:' nel sidebar (es. "Fonti: MEF · Eurostat")."""

    page_icon: str = ""
    """Icona per st.set_page_config (default: ``icon``)."""

    layout: str = "wide"
    """Layout Streamlit: "centered" o "wide"."""

    sidebar_state: str = "expanded"
    """Stato iniziale sidebar: "expanded", "collapsed", o "hidden"."""

    # campi extra per backward compat
    extra: dict[str, Any] = field(default_factory=dict)


def run_dashboard(config: DashboardConfig, pages: dict[str, Any]) -> None:
    """All-in-one: set_page_config + apply_branding + navigation + run.

    Args:
        config: Configurazione dashboard.
        pages: Dict di pagine ``{section: [st.Page(...)]}``.

    """
    import streamlit as st

    from lab_connectors.branding import apply_branding

    st.set_page_config(
        page_title=config.title,
        page_icon=config.page_icon or config.icon,
        layout=config.layout,
        initial_sidebar_state=config.sidebar_state,
    )

    apply_branding(
        repo_name=config.repo_name,
        repo_url=config.repo_url,
        sources_text=config.sources_text,
    )

    pg = st.navigation(pages, position="sidebar")
    pg.run()


_LAZY_IMPORTS: dict[str, str] = {
    "require_data": "lab_connectors.dashboard._guard",
    "init_sources": "lab_connectors.dashboard.sources",
    "make_cached_sources": "lab_connectors.dashboard.sources",
    "years_for_slug": "lab_connectors.dashboard.sources",
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_IMPORTS:
        import importlib

        module = importlib.import_module(_LAZY_IMPORTS[name])
        result = getattr(module, name)
        globals()[name] = result
        return result
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DashboardConfig",
    "init_sources",
    "make_cached_sources",
    "require_data",
    "run_dashboard",
    "years_for_slug",
]
