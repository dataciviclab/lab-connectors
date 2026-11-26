"""Tema Streamlit allineato allo standard di brand.

I valori vengono da `infra/lab-ops/standards/brand.md` (accenti di marca) e dalle
superfici già in uso nelle dashboard. Un solo posto da cui generare il blocco
`[theme]` dei `config.toml`:

    from lab_connectors.theme import streamlit_config

    print(streamlit_config("dark"))

Cambiare un accento qui significa rigenerare i config, non modificarli a mano in
trentasette repository.
"""

from __future__ import annotations

from typing import Literal

ThemeBase = Literal["light", "dark"]

#: accento di marca su fondo chiaro — 5,17:1 su bianco
ACCENT_LIGHT = "#2563EB"
#: accento di marca su fondo scuro — 7,43:1 su #0E1117
ACCENT_DARK = "#60A5FA"

#: superfici già in uso nelle dashboard (nessuna nuova tinta introdotta)
BACKGROUND_DARK = "#0E1117"
SURFACE_DARK = "#262730"
TEXT_ON_DARK = "#FAFAFA"
BACKGROUND_LIGHT = "#FFFFFF"
TEXT_ON_LIGHT = "#0F172A"


def streamlit_theme(base: ThemeBase = "dark") -> dict[str, str]:
    """Blocco `[theme]` per Streamlit.

    Args:
        base: tema di partenza.

    Returns:
        Dizionario chiave/valore pronto per il TOML.

    """
    if base == "light":
        return {
            "base": "light",
            "primaryColor": ACCENT_LIGHT,
            "backgroundColor": BACKGROUND_LIGHT,
            "textColor": TEXT_ON_LIGHT,
            "font": "sans serif",
        }
    return {
        "base": "dark",
        "primaryColor": ACCENT_DARK,
        "backgroundColor": BACKGROUND_DARK,
        "secondaryBackgroundColor": SURFACE_DARK,
        "textColor": TEXT_ON_DARK,
        "font": "sans serif",
    }


def streamlit_config(base: ThemeBase = "dark", *, server_headless: bool = True) -> str:
    """Contenuto completo di `.streamlit/config.toml`.

    Args:
        base: tema di partenza.
        server_headless: include `[server] headless = true` (default delle dashboard).

    Returns:
        Testo TOML con newline finale.

    """
    lines: list[str] = []
    if server_headless:
        lines += ["[server]", "headless = true", ""]
    lines.append("[theme]")
    lines += [f'{key} = "{value}"' for key, value in streamlit_theme(base).items()]
    return "\n".join(lines) + "\n"


__all__ = [
    "ACCENT_DARK",
    "ACCENT_LIGHT",
    "BACKGROUND_DARK",
    "BACKGROUND_LIGHT",
    "SURFACE_DARK",
    "TEXT_ON_DARK",
    "TEXT_ON_LIGHT",
    "streamlit_config",
    "streamlit_theme",
]
