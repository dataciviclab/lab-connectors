"""Formatting helpers per dashboard Streamlit.

Usage::

    from lab_connectors.formatters import fmt_eur, fmt_num, fmt_pct

    st.metric("Entrate", fmt_eur(1_500_000))  # "€ 1.500.000"
    st.metric("Enti", fmt_num(8701))           # "8.701"
    st.metric("Variazione", fmt_pct(0.1234))  # "+12.3%"
"""

from __future__ import annotations


def fmt_eur(value: float | int | None, *, compact: bool = False) -> str:
    """Formatta un valore come valuta EUR.

    Args:
        value: Valore numerico.
        compact: Se ``True``, usa formati compatti (mld, mln).

    Examples:
        >>> fmt_eur(1_500_000)
        '€ 1.500.000'
        >>> fmt_eur(2_500_000_000, compact=True)
        '€ 2,5 mld'

    """
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
    """Formatta un numero con separatori delle migliaia (italiano).

    Examples:
        >>> fmt_num(8701)
        '8.701'

    """
    if value is None:
        return "—"
    return f"{int(value):,}".replace(",", ".")


def fmt_pct(value: float | None, *, decimals: int = 1) -> str:
    """Formatta una frazione come percentuale.

    Args:
        value: Frazione (0.1234 = 12.3%).
        decimals: Cifre decimali.

    Examples:
        >>> fmt_pct(0.1234)
        '+12.3%'
        >>> fmt_pct(-0.05)
        '-5.0%'

    """
    if value is None:
        return "—"
    v = float(value) * 100
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.{decimals}f}%".replace("-", "−")


__all__ = ["fmt_eur", "fmt_num", "fmt_pct"]
