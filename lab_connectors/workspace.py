"""Workspace discovery layer for DataCivicLab.

Trova la root del workspace e tutti i repo al suo interno,
indipendentemente dalla struttura delle directory.

Usage::

    from lab_connectors.workspace import get_workspace_root, find_repos

    root = get_workspace_root()
    repos = find_repos()  # scan ricorsivo per registry/registry.json
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

# -- Workspace root -----------------------------------------------------------


@lru_cache(maxsize=1)
def get_workspace_root() -> Path:
    """Restituisce la root del workspace DataCivicLab.

    Risoluzione (in ordine):
    1. Env var ``DCL_WORKSPACE_ROOT``
    2. Walk up da questo file fino a trovare ``toolkit/`` o ``Makefile``
    3. CWD come fallback
    """
    # 1. Explicit env var
    env = os.environ.get("DCL_WORKSPACE_ROOT")
    if env:
        return Path(env).expanduser().resolve()

    # 2. Walk up looking for workspace markers
    current = Path(__file__).resolve().parent
    for _ in range(10):  # max 10 levels up
        if (current / "toolkit").is_dir() or (current / "Makefile").is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent

    # 3. Fallback: CWD
    return Path.cwd().resolve()


# -- Repo discovery -----------------------------------------------------------

_MARKERS = ("registry.json",)  # canonical markers for a DataCivicLab repo
_DIRS_MARKERS = ("registry", "datasets")  # directories that indicate a repo


@lru_cache(maxsize=1)
def find_repos(root: Path | None = None) -> dict[str, Path]:
    """Trova tutti i repo nel workspace scanando ricorsivamente.

    Cerca:
    - ``registry/registry.json`` (marker canonico)
    - ``datasets/`` directory (marker secondario per repo senza registry)
    - ``candidates/`` directory (marker per dataset-incubator)

    Restituisce dict ``{slug: repo_root}`` ordinate per slug.

    Args:
        root: Workspace root. Se None, usa ``get_workspace_root()``.

    Returns:
        Dict slug → Path del repo root.

    """
    if root is None:
        root = get_workspace_root()

    repos: dict[str, Path] = {}

    # Scan ricorsivo, max 4 livelli di profondità
    for marker in _walk_markers(root, max_depth=4):
        # Determine repo root based on marker type
        if marker.name == ".marker" and marker.parent.name in ("datasets", "candidates"):
            # Synthetic marker for datasets/ or candidates/ directory
            repo_root = marker.parent.parent
        else:
            # Real registry/registry.json
            repo_root = marker.parent.parent  # registry/registry.json → repo_root

        # Leggi slug dal marker
        slug = _slug_from_registry(marker)
        if slug:
            repos[slug] = repo_root

    return dict(sorted(repos.items()))

    return dict(sorted(repos.items()))


def find_repo(slug: str, root: Path | None = None) -> Path | None:
    """Trova un repo specifico per slug.

    Args:
        slug: Slug del repo (es. "rna-aiuti-stato").
        root: Workspace root. Se None, usa ``get_workspace_root()``.

    Returns:
        Path del repo root, o None se non trovato.

    """
    repos = find_repos(root)
    return repos.get(slug)


def _walk_markers(root: Path, max_depth: int = 4):  # type: ignore[no-untyped-def]
    """Walk ricorsivo che yield i path dei marker trovati.

    Cerca:
    - ``registry/registry.json`` (marker primario)
    - ``datasets/`` directory (marker secondario per repo senza registry)
    - ``candidates/`` directory (marker per dataset-incubator)
    """
    root_str = str(root)
    seen: set[str] = set()

    def _walk(current: Path, depth: int):  # type: ignore[no-untyped-def]
        if depth >= max_depth:
            return
        try:
            for entry in current.iterdir():
                if not entry.is_dir():
                    continue
                # Skip hidden dirs, node_modules, .git, __pycache__
                if entry.name.startswith(".") or entry.name in ("node_modules", "__pycache__"):
                    continue
                # Skip if outside workspace
                if not str(entry).startswith(root_str):
                    continue

                # Check for registry/registry.json (primary marker)
                marker = entry / "registry" / "registry.json"
                if marker.is_file():
                    marker_str = str(marker)
                    if marker_str not in seen:
                        seen.add(marker_str)
                        yield marker
                    # Don't recurse into repo dirs
                    continue

                # Check for datasets/ directory (secondary marker)
                if (entry / "datasets").is_dir():
                    # Yield a synthetic marker for slug extraction
                    synthetic = entry / "datasets" / ".marker"
                    marker_str = str(synthetic)
                    if marker_str not in seen:
                        seen.add(marker_str)
                        yield synthetic
                    # Don't recurse into repo dirs
                    continue

                # Check for candidates/ directory (marker for dataset-incubator)
                if (entry / "candidates").is_dir():
                    # Yield a synthetic marker for slug extraction
                    synthetic = entry / "candidates" / ".marker"
                    marker_str = str(synthetic)
                    if marker_str not in seen:
                        seen.add(marker_str)
                        yield synthetic
                    # Don't recurse into repo dirs
                    continue

                # Recurse
                yield from _walk(entry, depth + 1)
        except PermissionError:
            pass

    yield from _walk(root, 0)


def _slug_from_registry(registry_json: Path) -> str | None:
    """Estrae lo slug dal file registry.json o dalla directory datasets/candidates/."""
    # Handle synthetic markers for datasets/ or candidates/ directories
    if registry_json.name == ".marker" and registry_json.parent.name in ("datasets", "candidates"):
        # Use parent directory name as slug
        return registry_json.parent.parent.name

    # Handle real registry.json files
    import json

    try:
        with open(registry_json) as f:
            data = json.load(f)
        return data.get("repo") or data.get("slug")
    except (json.JSONDecodeError, OSError):
        return None


# -- Local data detection ----------------------------------------------------


@lru_cache(maxsize=128)
def detect_local_root(repo_root: Path) -> str | None:
    """Rileva ``out/data/`` all'interno di un repo specifico.

    Args:
        repo_root: Root del repo da cui cercare.

    Returns:
        Path ``out/data/`` se trovato, altrimenti None.

    """
    data_dir = repo_root / "out" / "data"
    if data_dir.is_dir() and any(data_dir.rglob("*.parquet")):
        return str(data_dir)
    return None


__all__ = [
    "detect_local_root",
    "find_repo",
    "find_repos",
    "get_workspace_root",
]
