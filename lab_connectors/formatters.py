"""Formatting helpers per dashboard Streamlit.

Usage::

    from lab_connectors.formatters import fmt_eur, fmt_num, fmt_pct

    st.metric("Entrate", fmt_eur(1_500_000))  # "€ 1.500.000"
    st.metric("Enti", fmt_num(8701))           # "8.701"
    st.metric("Variazione", fmt_pct(0.1234))  # "+12.3%"
"""

from __future__ import annotations

import math


def _safe_number(value: float | int | None) -> float | int | None:
    """Handle None, NaN, pd.NA — restituisce None per valori non numerici."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        import pandas as pd

        if value is pd.NA:
            return None
    except ImportError:
        pass
    return value


def fmt_eur(value: float | int | None, *, compact: bool = False) -> str:
    """Formatta un valore come valuta EUR."""
    value = _safe_number(value)
    if value is None:
        return "—"
    v = float(value)
    if compact:
        if abs(v) >= 1e9:
            return (
                f"€ {v / 1e9:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".") + " mld"
            )
        if abs(v) >= 1e6:
            return f"€ {v / 1e6:,.0f}".replace(",", ".") + " mln"
    return f"€ {v:,.0f}".replace(",", ".")


def fmt_num(value: float | int | None) -> str:
    """Formatta un numero con separatori delle migliaia (italiano)."""
    value = _safe_number(value)
    if value is None:
        return "—"
    return f"{int(value):,}".replace(",", ".")


def fmt_pct(value: float | None, *, decimals: int = 1) -> str:
    """Formatta una percentuale."""
    value = _safe_number(value)
    if value is None:
        return "—"
    v = float(value)
    if 0 < abs(v) <= 1:
        v *= 100
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.{decimals}f}%".replace("-", "−")


__all__ = ["fmt_eur", "fmt_num", "fmt_pct"]
