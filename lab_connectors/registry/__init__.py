"""Registry — modelli e client per registry/registry.json.

Usage::

    from lab_connectors.registry import load_registry
    from lab_connectors.registry.models import Registry, Dataset, Signal

    reg = load_registry(Path("repo/registry/registry.json"))
    for sig in reg.signals:
        print(sig.id, sig.status)
"""

from lab_connectors.registry.availability import (
    latest_published_year,
    published_years,
    year_range,
)
from lab_connectors.registry.client import (
    load_registry,
    load_registry_github,
    load_registry_local,
    load_registry_url,
    registry_to_dict,
)
from lab_connectors.registry.models import (
    Column,
    Dataset,
    Location,
    Mart,
    Registry,
    Run,
    Signal,
)
from lab_connectors.registry.slugs import URL_SLUG_OVERRIDES, to_url_slug

__all__ = [
    "URL_SLUG_OVERRIDES",
    "Column",
    "Dataset",
    "Location",
    "Mart",
    "Registry",
    "Run",
    "Signal",
    "latest_published_year",
    "load_registry",
    "load_registry_github",
    "load_registry_local",
    "load_registry_url",
    "published_years",
    "registry_to_dict",
    "to_url_slug",
    "year_range",
]
