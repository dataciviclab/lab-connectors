"""Branding DataCivicLab per le dashboard Streamlit.

Il marchio è spedito col pacchetto (`lab_connectors/assets/brand/`): copia verificata
degli asset canonici in `infra/lab-ops/standards/assets/logo/`. Nessuna richiesta di
rete all'avvio e nessuna dipendenza dal repository del sito.

La variante (chiara o scura) segue il tema dell'app: su fondo `#0E1117` il marchio
in inchiostro sarebbe invisibile, e viceversa.

Uso::

    from lab_connectors.branding import apply_branding

    apply_branding()
    apply_branding(repo_name="open-coesione", repo_url="https://github.com/dataciviclab/open-coesione")
"""

from __future__ import annotations

import os
from importlib import resources
from typing import Literal

SITE_URL = "https://dataciviclab.org"
DEFAULT_LICENSE = "CC BY 4.0"

Variant = Literal["auto", "light", "dark"]
ThemeBase = Literal["light", "dark"]

#: file di brand per variante, dentro `lab_connectors/assets/brand/`
_FILES: dict[str, str] = {"light": "symbol.svg", "dark": "symbol-on-dark.svg"}
_ICON_FILE = "favicon.svg"


def _asset_path(name: str) -> str:
    """Percorso assoluto di un asset di brand dentro il pacchetto installato.

    Args:
        name: nome del file in `assets/brand/`.

    Returns:
        Percorso usabile da `st.logo`, che accetta file SVG su disco.

    Raises:
        FileNotFoundError: se il pacchetto è installato senza gli asset.

    """
    path = str(resources.files("lab_connectors").joinpath("assets", "brand", name))
    if not os.path.isfile(path):
        raise FileNotFoundError(f"asset di brand mancante: {path}. Reinstalla lab-connectors.")
    return path


def detect_variant() -> ThemeBase:
    """Tema in uso, letto da Streamlit; default chiaro.

    Il default è chiaro perché è il default di Streamlit: un'app senza tema
    configurato è chiara, e mostrare il marchio bianco su fondo bianco lo
    renderebbe invisibile.
    """
    try:
        import streamlit as st

        theme = getattr(st.context, "theme", None)
        kind = getattr(theme, "type", None) if theme is not None else None
        if kind in ("light", "dark"):
            return kind
    except Exception:
        pass
    return "light"


def apply_branding(
    *,
    repo_name: str = "",
    repo_url: str = "",
    size: Literal["small", "medium", "large"] = "large",
    variant: Variant = "auto",
    license_name: str | None = DEFAULT_LICENSE,
) -> None:
    """Applica marchio e attribuzione alla dashboard.

    Args:
        repo_name: nome del repo. Se vuoto, nessun link al repository.
        repo_url: URL del repo, mostrato solo insieme a `repo_name`.
        size: dimensione del marchio nella sidebar.
        variant: ``"auto"`` segue il tema dell'app; ``"light"``/``"dark"`` forzano.
        license_name: licenza da mostrare. ``None`` la omette: usarlo quando il
            dataset non è CC BY 4.0 (il valore era scritto fisso, e sbagliato per
            i repo con licenza diversa).

    """
    import streamlit as st

    chosen = detect_variant() if variant == "auto" else variant
    st.logo(
        _asset_path(_FILES[chosen]),
        size=size,
        icon_image=_asset_path(_ICON_FILE),
        link=SITE_URL,
    )

    st.sidebar.markdown("---")
    credit = f"[DataCivicLab]({SITE_URL}/)"
    if repo_name and repo_url:
        credit += f" · [{repo_name}]({repo_url})"
    if license_name:
        credit += f" · {license_name}"
    st.sidebar.caption(credit)


__all__ = ["DEFAULT_LICENSE", "SITE_URL", "apply_branding", "detect_variant"]
