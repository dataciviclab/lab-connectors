"""Empty state guard per pagine Streamlit.

Usage::

    from lab_connectors.dashboard import require_data

    df = load_my_data()
    require_data(df)  # mostra warning e stop se vuoto
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


_DEFAULT_MESSAGE = "Nessun dato disponibile. Esegui `make run` prima."


def require_data(
    df: pd.DataFrame | None,
    message: str = _DEFAULT_MESSAGE,
) -> None:
    """Mostra ``st.warning`` e chiama ``st.stop()`` se il DataFrame e' vuoto.

    Args:
        df: DataFrame da verificare. Se ``None`` o vuoto, mostra il messaggio.
        message: Messaggio di avviso (default: "Nessun dato disponibile.").

    """
    if df is None:
        _stop_with_warning(message)
        return

    if hasattr(df, "empty") and df.empty:
        _stop_with_warning(message)


def _stop_with_warning(message: str) -> None:
    """Importa streamlit lazy e mostra warning + stop."""
    import streamlit as st

    st.warning(message)
    st.stop()
