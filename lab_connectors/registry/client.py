"""Client per caricare registry da qualsiasi sorgente.

Usage::

    from lab_connectors.registry.client import load_registry

    # Da path locale
    reg = load_registry(Path("rna-aiuti-stato/registry/registry.json"))

    # Da URL
    reg = load_registry("https://raw.githubusercontent.com/.../registry.json")

    # Da repo GitHub (org/dataciviclab default)
    reg = load_registry_github("rna-aiuti-stato")
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lab_connectors.registry.models import Registry


def load_registry(source: str | Path) -> Registry:
    """Carica un registry da path locale, URL o repo name.

    Auto-detect:
    - ``Path`` → lettura locale
    - ``str`` che inizia con ``http`` → URL diretto
    - ``str`` → repo name su GitHub
    """
    if isinstance(source, Path):
        return load_registry_local(source)
    s = str(source)
    if s.startswith(("http://", "https://")):
        return load_registry_url(s)
    return load_registry_github(s)


def load_registry_local(path: str | Path) -> Registry:
    """Carica un registry da file locale."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Registry non trovato: {p}")
    text = p.read_text(encoding="utf-8")
    return _parse_registry(text)


def load_registry_url(url: str) -> Registry:
    """Carica un registry da URL."""
    resp = _http_get(url)
    return _parse_registry(resp.text)


def load_registry_github(repo: str, org: str = "dataciviclab") -> Registry:
    """Carica un registry da GitHub (raw.githubusercontent.com)."""
    url = f"https://raw.githubusercontent.com/{org}/{repo}/main/registry/registry.json"
    return load_registry_url(url)


def registry_to_dict(reg: Registry) -> dict:
    """Convert a Registry to dict (backward compat con lab-dashboard)."""
    from dataclasses import asdict

    return asdict(reg)


# -- Internal ----------------------------------------------------------------


def _parse_registry(text: str) -> Registry:
    """Parse JSON text → Registry."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON non valido: {e}") from None
    return Registry.from_dict(data)


def _http_get(url: str) -> Any:
    """HTTP GET con retry."""
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    return resp


__all__ = [
    "load_registry",
    "load_registry_github",
    "load_registry_local",
    "load_registry_url",
    "registry_to_dict",
]
