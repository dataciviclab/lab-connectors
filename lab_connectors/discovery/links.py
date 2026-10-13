"""Estrazione e raggruppamento di link dati da pagine HTML.

Contratto centrale per l'estrazione di link a file dati da pagine HTML.
Zero dipendenze esterne — solo stdlib.

Consumer:
  - source-observatory/collectors/html.py  → inventory HTML
  - toolkit (via lab_connectors)           → scaffold, scout
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlparse

# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------

# Estensioni di file dati riconosciute. Ordinate per lunghezza decrescente
# per matchare .xlsx prima di .xls e .geojson prima di .json.
DATA_EXTENSIONS = frozenset(
    {
        ".csv",
        ".json",
        ".xlsx",
        ".xls",
        ".ods",
        ".zip",
        ".xml",
        ".parquet",
        ".geojson",
        ".rdf",
    }
)

# Pattern per estrarre prefisso e anni dal filename
_PREFIX_RE = re.compile(r"^([A-Z][A-Z0-9]{1,7})")
_YEAR_RE = re.compile(r"(20[012]\d)")

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class DataLink:
    """Un link a un file dati estratto da HTML.

    Attributes:
        url: URL assoluto del file.
        format: Formato in maiuscolo (CSV, XLSX, ZIP, ...).
        title: Titolo estratto da aria-label o title attribute.
        prefix: Prefisso categorico estratto dal filename.
        years: Anni (20xx) trovati nel filename.
        page_url: URL della pagina HTML da cui è stato estratto.

    """

    url: str
    format: str
    title: str = ""
    prefix: str = ""
    years: list[int] = field(default_factory=list)
    page_url: str = ""


@dataclass
class LinkGroup:
    """Gruppo di link che appartengono allo stesso dataset.

    Attributes:
        group_id: Identificatore univoco del gruppo (es. prefisso).
        title: Titolo descrittivo del gruppo.
        prefix: Prefisso comune.
        year_range: Anni minimo e massimo coperti.
        formats: Formati disponibili.
        links: Lista dei DataLink del gruppo.
        count: Numero di link nel gruppo.

    """

    group_id: str
    title: str
    prefix: str
    year_range: list[int]
    formats: set[str]
    links: list[DataLink]
    count: int = 0


# ---------------------------------------------------------------------------
# Helpers pubblici (usati anche da SO e altri consumer)
# ---------------------------------------------------------------------------


def extract_filename(url: str) -> str:
    """Estrae il filename (senza estensione) da un URL."""
    path = urlparse(url).path
    name = path.rsplit("/", 1)[-1] if "/" in path else path
    name = unquote(name)
    dot = name.rfind(".")
    if dot > 0:
        name = name[:dot]
    return name


def extract_prefix(filename: str) -> str:
    """Estrae un prefisso categorico dal filename.

    - Se contiene underscore, prende la prima parte.
    - Altrimenti matcha una run di maiuscole/digits all'inizio.
    - Fallback: primi 6 caratteri.
    """
    if "_" in filename:
        return filename.split("_")[0]
    m = _PREFIX_RE.match(filename)
    if m:
        return m.group(1)
    return filename[:6]


def extract_years(filename: str) -> list[int]:
    """Estrae tutti gli anni (20xx) presenti nel filename."""
    return [int(y) for y in _YEAR_RE.findall(filename)]


def resolve_format(
    url: str, data_extensions: frozenset[str] | set[str] | None = None
) -> str | None:
    """Determina il formato dall'estensione del file nell'URL.

    Gestisce anche URL Liferay-style (es. ``/documents/09/file.csv/uuid-xyz``)
    dove l'estensione e' un segmento di path seguito da un UUID, non la coda.

    Args:
        url: URL da classificare.
        data_extensions: Estensioni da riconoscere (default: DATA_EXTENSIONS).

    """
    exts = data_extensions or DATA_EXTENSIONS
    lower = url.lower()
    path = url.split("?")[0].lower().rstrip("/")
    for ext in sorted(exts, key=len, reverse=True):
        # 1) Estensione in coda al path (caso standard)
        if path.endswith(ext):
            return ext.lstrip(".").upper()
        # 2) Estensione come segmento intermedio seguito da un ulteriore
        #    segmento lungo >= 8 (UUID/hash Liferay: .../file.csv/45e7ec1b-...)
        marker = ext + "/"
        idx = path.find(marker)
        if idx != -1:
            tail = path[idx + len(marker) :]
            if "/" not in tail and len(tail) >= 8:
                return ext.lstrip(".").upper()
        # 3) fallback: estensione in coda a tutto l'URL (query esclusa)
        check = lower.rstrip("/")
        if check.endswith(ext):
            return ext.lstrip(".").upper()
    return None


# ---------------------------------------------------------------------------
# Parser HTML
# ---------------------------------------------------------------------------


class _DataLinkParser(HTMLParser):
    """Parser HTML che estrae link a file dati."""

    def __init__(self, base_url: str, data_extensions: frozenset[str]) -> None:
        super().__init__()
        self.base_url = base_url
        self.data_extensions = data_extensions
        self.links: list[DataLink] = []
        self._seen: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() not in ("a", "area"):
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href", "") or attrs_dict.get("xlink:href", "")
        if not href:
            return
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            return

        full_url = urljoin(self.base_url, href)
        fmt = resolve_format(full_url, self.data_extensions)
        if fmt is None:
            return

        if full_url in self._seen:
            return
        self._seen.add(full_url)

        title = (attrs_dict.get("aria-label") or attrs_dict.get("title") or "").strip()
        filename = extract_filename(full_url)
        prefix = extract_prefix(filename)
        years = extract_years(filename)

        self.links.append(
            DataLink(
                url=full_url,
                format=fmt,
                title=title,
                prefix=prefix,
                years=years,
            )
        )


# ---------------------------------------------------------------------------
# Funzioni pubbliche
# ---------------------------------------------------------------------------


def extract_data_links(
    base_url: str,
    html: str,
    *,
    data_extensions: set[str] | frozenset[str] | None = None,
) -> list[DataLink]:
    """Estrae link a file dati da HTML.

    Args:
        base_url: URL di base per risolvere link relativi.
        html: Testo HTML da parsare.
        data_extensions: Estensioni da riconoscere (default: DATA_EXTENSIONS).

    Returns:
        Lista di DataLink, deduplicati per URL, ordinati per apparizione.

    """
    exts = frozenset(data_extensions) if data_extensions is not None else DATA_EXTENSIONS
    try:
        parser = _DataLinkParser(base_url, exts)
        parser.feed(html)
        return parser.links
    except Exception:
        return []


def group_links(links: list[DataLink]) -> list[LinkGroup]:
    """Raggruppa link in dataset basandosi su prefisso.

    Strategia:
    1. Raggruppa per ``prefix`` (quando presente).
    2. Link senza prefix vanno in un gruppo ``other``.

    Args:
        links: Lista di DataLink da raggruppare.

    Returns:
        Lista di LinkGroup ordinata per dimensione discendente.

    """
    by_prefix: dict[str, list[DataLink]] = {}
    for link in links:
        p = link.prefix or "_other"
        by_prefix.setdefault(p, []).append(link)

    groups: list[LinkGroup] = []
    for prefix, group in by_prefix.items():
        years: set[int] = set()
        formats: set[str] = set()
        for link in group:
            years.update(link.years)
            formats.add(link.format)

        group_id = prefix if prefix != "_other" else "other"
        title = group[0].title or prefix

        groups.append(
            LinkGroup(
                group_id=group_id,
                title=title,
                prefix=prefix if prefix != "_other" else "",
                year_range=sorted(years),
                formats=formats,
                links=group,
                count=len(group),
            )
        )

    groups.sort(key=lambda g: g.count, reverse=True)
    return groups


def extract_candidate_links(base_url: str, html_text: str) -> list[str]:
    """Versione legacy: ritorna solo URL (nessun metadato)."""
    links = extract_data_links(base_url, html_text)
    return [link.url for link in links]


# Alias backward-compat (i vecchi nomi privati sono ora pubblici)
_extract_prefix = extract_prefix
_extract_years = extract_years
_resolve_format = resolve_format
