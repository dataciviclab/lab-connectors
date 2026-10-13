"""Classificazione URL e content-type — funzioni pure, zero I/O.

Determina il tipo di risorsa da URL e header HTTP senza effettuare chiamate di rete.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# Estensioni candidate per file dati
CANDIDATE_EXTENSIONS = (".csv", ".xlsx", ".xls", ".zip", ".json", ".parquet", ".geojson")
EXTENDED_EXTENSIONS = CANDIDATE_EXTENSIONS + (".sdmx", ".tds", ".xml")

# Tipi preview supportati
PREVIEW_KINDS = frozenset({"csv", "json", "xlsx", "xls", "tsv"})


def is_html_content(content_type: str | None) -> bool:
    """Rileva se Content-Type indica HTML."""
    return bool(content_type and "html" in content_type.lower())


def is_file_like(url: str, content_type: str | None, content_disposition: str | None) -> bool:
    """Rileva se URL/headers sembra puntare a un file di dati."""
    lowered = url.lower()
    if any(ext in lowered for ext in CANDIDATE_EXTENSIONS):
        return True
    if content_disposition and "attachment" in content_disposition.lower():
        return True
    if content_type and not is_html_content(content_type):
        ct_lower = content_type.lower()
        return any(token in ct_lower for token in ("csv", "excel", "spreadsheetml", "zip", "json"))
    return False


def is_sdmx_url(url: str) -> bool:
    """Rileva se URL punta a un endpoint SDMX."""
    lowered = url.lower()
    return any(pattern in lowered for pattern in ("/dataflow/", "/sdmx/", "sdmx", "?flow="))


def is_sparql_endpoint(url: str, content_type: str | None = None) -> bool:
    """Rileva se URL punta a un endpoint SPARQL.

    Controlla:
    - Path URL contenente ``/sparql`` (pattern piu' comune)
    - Content-Type contenente ``sparql-results`` o ``sparql``
    """
    lowered = url.lower()
    if "/sparql" in lowered:
        return True
    if content_type:
        ct = content_type.lower()
        if "sparql-results" in ct or "sparql" in ct:
            return True
    return False


def resolve_preview_kind(
    url: str,
    content_type: str | None = None,
    content_disposition: str | None = None,
) -> str | None:
    """Determina il formato preview (csv, json, xlsx, xls, tsv) da URL/headers.

    Ordine: estensione URL → Content-Disposition filename → Content-Type.
    """
    # 1. Da estensione URL
    parsed = urlparse(url)
    path = parsed.path or ""
    if "." in path:
        ext = path.rsplit(".", 1)[-1].lower()
        if ext in PREVIEW_KINDS:
            return ext.upper()

    # 2. Da Content-Disposition (filename)
    fn = filename_from_content_disposition(content_disposition)
    if fn and "." in fn:
        ext = fn.rsplit(".", 1)[-1].lower()
        if ext in PREVIEW_KINDS:
            return ext.upper()

    # 3. Da Content-Type
    if content_type:
        ct_lower = content_type.lower()
        if "tab-separated" in ct_lower or ct_lower in ("text/tsv", "application/tsv"):
            return "TSV"
        if "csv" in ct_lower:
            return "CSV"
        if "json" in ct_lower:
            return "JSON"
        if "spreadsheetml" in ct_lower:
            return "XLSX"
        if "excel" in ct_lower or "xls" in ct_lower:
            return "XLS"

    return None


def filename_from_content_disposition(value: str | None) -> str | None:
    """Estrae filename da Content-Disposition (RFC 5987 / quoted / token)."""
    if not value:
        return None
    m = re.search(r"filename\*=(?:UTF-8''|utf-8'')([^;\s]+)", value)
    if m:
        from urllib.parse import unquote

        raw = m.group(1).strip().strip('"')
        return unquote(raw) if raw else None
    m = re.search(r'filename="([^"]+)"', value)
    if m:
        return m.group(1).strip() or None
    m = re.search(r"filename=([^;\s]+)", value)
    if m:
        return m.group(1).strip().strip('"') or None
    return None
