"""Discovery primitives per source exploration e link extraction.

Modulo condiviso tra SO e toolkit per:
- Estrazione link a file dati da HTML
- Classificazione URL e content-type
- Inference su nomi colonna e testo

Zero dipendenze da toolkit — solo stdlib e lab_connectors.http.
"""

from __future__ import annotations

from lab_connectors.discovery.classify import (
    CANDIDATE_EXTENSIONS,
    EXTENDED_EXTENSIONS,
    PREVIEW_KINDS,
    filename_from_content_disposition,
    is_file_like,
    is_html_content,
    is_sdmx_url,
    is_sparql_endpoint,
    resolve_preview_kind,
)
from lab_connectors.discovery.infer import (
    YEAR_COLUMN_HINTS,
    extract_years_from_columns,
    extract_years_from_filename,
    infer_granularity,
    infer_granularity_from_name_and_columns,
    infer_topics,
    infer_years,
    infer_years_from_columns,
    suggest_years,
)
from lab_connectors.discovery.links import (
    DATA_EXTENSIONS,
    DataLink,
    LinkGroup,
    extract_candidate_links,
    extract_data_links,
    extract_filename,
    extract_prefix,
    extract_years,
    group_links,
    resolve_format,
)

__all__ = [
    "CANDIDATE_EXTENSIONS",
    "DATA_EXTENSIONS",
    "EXTENDED_EXTENSIONS",
    "PREVIEW_KINDS",
    "YEAR_COLUMN_HINTS",
    "DataLink",
    "LinkGroup",
    "extract_candidate_links",
    "extract_data_links",
    "extract_filename",
    "extract_prefix",
    "extract_years",
    "extract_years_from_columns",
    "extract_years_from_filename",
    "filename_from_content_disposition",
    "group_links",
    "infer_granularity",
    "infer_granularity_from_name_and_columns",
    "infer_topics",
    "infer_years",
    "infer_years_from_columns",
    "is_file_like",
    "is_html_content",
    "is_sdmx_url",
    "is_sparql_endpoint",
    "resolve_format",
    "resolve_preview_kind",
    "suggest_years",
]
