"""Slug canonico delle URL pubbliche del DataCivicLab.

L'Explorer pubblica una pagina per dataset. Lo slug dell'URL non è sempre la
trasformazione meccanica ``_ -> -`` dello slug interno (``dataset.slug`` nel
registry): alcuni dataset hanno uno slug editoriale scelto a mano.

Questo modulo è l'unica fonte della mappatura, così i consumer (Explorer,
lab-dashboard, agent-context-builder) non tengono copie divergenti.

Usage::

    from lab_connectors.registry.slugs import to_url_slug

    to_url_slug("ispra_ru_base")       # "rifiuti-urbani"
    to_url_slug("aci_iscrizioni")      # "aci-iscrizioni"
"""

from __future__ import annotations

# Slug interni (underscore) -> slug URL pubblico (hyphen).
# Solo le eccezioni editoriali: la regola di default è meccanica.
URL_SLUG_OVERRIDES: dict[str, str] = {
    "aifa_spesa_consumo": "spesa-farmaceutica",
    "ispra_ru_base": "rifiuti-urbani",
    "civile_flussi": "flussi-giustizia-civile",
    "terna_capacita_rinnovabile": "capacita-rinnovabile",
    "terna_electricity_by_source": "produzione-elettrica-fonti",
    "camera_votazioni_sparql": "votazioni-camera",
    "camera_deputati_legislature": "camera-deputati",
    "camera_interventi": "attivita-aula",
    "camera_voti": "voti-deputati",
    "bdap_entrate_stato": "entrate-stato",
    "inps_pensioni_trimestrale": "pensioni-inps",
    "ade_cinque_per_mille": "cinque-per-mille",
    "istat_housing_crowding": "housing-crowding",
    "mit_incidentalita_mensile": "mit-incidentalita",
    "opencivitas_fsc_rso": "opencivitas-fsc-2025",
    "popolazione_istat_comunale_2019_2025": "popolazione-istat",
}


def to_url_slug(slug: str) -> str:
    """Converti lo slug interno nel corrispondente slug URL pubblico.

    Args:
        slug: Slug interno del dataset (``dataset.slug`` nel registry).

    Returns:
        Slug URL pubblico: override editoriale se presente, altrimenti
        trasformazione meccanica ``_`` -> ``-``.

    Example::

        >>> to_url_slug("istat_housing_crowding")
        'housing-crowding'
        >>> to_url_slug("aci_prime_iscrizioni")
        'aci-prime-iscrizioni'

    """
    return URL_SLUG_OVERRIDES.get(slug, slug.replace("_", "-"))


__all__ = ["URL_SLUG_OVERRIDES", "to_url_slug"]
