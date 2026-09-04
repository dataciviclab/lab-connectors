"""Branding DataCivicLab per dashboard Streamlit.

Logo centralizzato + sidebar attribution. Uso::

    from lab_connectors.branding import apply_branding
    apply_branding()
"""

from __future__ import annotations

_LOGO_URL = "https://raw.githubusercontent.com/dataciviclab/dataciviclab/main/public/logo.jpg"
_ICON_URL = "https://raw.githubusercontent.com/dataciviclab/dataciviclab/main/public/icon.svg"


def apply_branding(
    *,
    repo_name: str = "",
    repo_url: str = "",
    size: str = "large",
) -> None:
    """Applica logo DataCivicLab + sidebar attribution.

    Chiamare in ``app.py`` dopo ``st.set_page_config()``.

    Args:
        repo_name: Nome del repo (es. "rna-aiuti-stato"). Se vuoto, solo il logo.
        repo_url: URL del repo GitHub. Se fornito con repo_name, mostra link.
        size: Dimensione logo ("small", "medium", "large").

    """
    import streamlit as st

    st.logo(
        _LOGO_URL,
        size=size,
        icon_image=_ICON_URL,
        link="https://dataciviclab.org",
    )

    st.sidebar.markdown("---")
    if repo_name and repo_url:
        st.sidebar.caption(
            f"[DataCivicLab](https://dataciviclab.org/) · [{repo_name}]({repo_url}) · CC BY 4.0"
        )
    else:
        st.sidebar.caption("[DataCivicLab](https://dataciviclab.org/) · CC BY 4.0")


__all__ = ["apply_branding"]
