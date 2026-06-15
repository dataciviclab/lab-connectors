"""MCP server per GitHub Discussions via GraphQL API.

Espone tool per leggere, cercare, creare discussion e commenti.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from lab_connectors.mcp import create_mcp_server, guard_timed

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

# ruff: noqa: E402
from github_discussions_client import (
    add_discussion_comment as add_discussion_comment_impl,
)
from github_discussions_client import (
    create_discussion as create_discussion_impl,
)
from github_discussions_client import (
    get_discussion as get_discussion_impl,
)
from github_discussions_client import (
    get_discussion_comments as get_discussion_comments_impl,
)
from github_discussions_client import (
    get_discussion_summary as get_discussion_summary_impl,
)
from github_discussions_client import (
    list_discussions as list_discussions_impl,
)
from github_discussions_client import (
    search_discussions as search_discussions_impl,
)

mcp = create_mcp_server(
    name="github-discussions",
    instructions=(
        "Connector MCP per GitHub Discussions via GraphQL. "
        "Permette di leggere, cercare, creare discussion e aggiungere commenti top-level. "
        "Tutti i tool accettano repo_full_name nel formato owner/repo. "
        "La search è full-text su titolo, body e commenti. "
        "La paginazione cursor-based è supportata in list_discussions."
    ),
)

SERVER_NAME = "github-discussions"


@mcp.tool(
    description=(
        "Elenca le GitHub Discussions di un repository, ordinate per UPDATED_AT discendente. "
        "Opzionalmente filtra per categoria (applicato lato client dopo paginazione — "
        "con paginazione attiva, discussion_count puo' essere 0 anche se discussioni "
        "della categoria esistono piu' avanti). "
        "Supporta cursor pagination: passa il valore 'end_cursor' della risposta "
        "precedente come 'after' per la pagina successiva."
    ),
    structured_output=True,
)
def github_list_discussions(
    repo_full_name: str,
    category_name: str | None = None,
    limit: int = 10,
    after: str | None = None,
    before: str | None = None,
) -> dict[str, Any]:
    """Elenca le discussioni di un repo con paginazione cursor."""
    return guard_timed(
        list_discussions_impl,
        "github_list_discussions",
        repo_full_name,
        category_name,
        limit,
        after,
        before,
        logger_name=SERVER_NAME,
    )


@mcp.tool(
    description=(
        "Restituisce una GitHub Discussion. "
        "mode=summary restituisce solo un estratto del body (default excerpt_chars=500). "
        "mode=full restituisce il body intero (default, backward compat)."
    ),
    structured_output=True,
)
def github_get_discussion(
    repo_full_name: str, number: int, mode: str = "full", excerpt_chars: int = 500
) -> dict[str, Any]:
    """Restituisce una discussion con body intero o riepilogo."""
    return guard_timed(
        get_discussion_impl,
        "github_get_discussion",
        repo_full_name,
        number,
        mode,
        excerpt_chars,
        logger_name=SERVER_NAME,
    )


@mcp.tool(
    description="Restituisce un riepilogo corto di una GitHub Discussion.",
    structured_output=True,
)
def github_get_discussion_summary(
    repo_full_name: str, number: int, excerpt_chars: int = 280
) -> dict[str, Any]:
    """Restituisce un estratto corto di una discussion."""
    return guard_timed(
        get_discussion_summary_impl,
        "github_get_discussion_summary",
        repo_full_name,
        number,
        excerpt_chars,
        logger_name=SERVER_NAME,
    )


@mcp.tool(
    description=(
        "Restituisce commenti top-level e reply annidate di una GitHub Discussion. "
        "mode=summary tronca body a excerpt_chars (default 200). "
        "mode=full restituisce body interi (default, backward compat)."
    ),
    structured_output=True,
)
def github_get_discussion_comments(
    repo_full_name: str,
    number: int,
    limit: int = 20,
    mode: str = "full",
    excerpt_chars: int = 200,
) -> dict[str, Any]:
    """Restituisce commenti e reply annidate di una discussion."""
    return guard_timed(
        get_discussion_comments_impl,
        "github_get_discussion_comments",
        repo_full_name,
        number,
        limit,
        mode,
        excerpt_chars,
        logger_name=SERVER_NAME,
    )


@mcp.tool(
    description=(
        "Cerca discussions in un repository per testo libero (titolo, body, commenti). "
        "Usa la GitHub Search API — i risultati sono limitati al repository specificato."
    ),
    structured_output=True,
)
def github_search_discussions(repo_full_name: str, query: str, limit: int = 10) -> dict[str, Any]:
    """Cerca discussion per testo libero su titolo, body e commenti."""
    return guard_timed(
        search_discussions_impl,
        "github_search_discussions",
        repo_full_name,
        query,
        limit,
        logger_name=SERVER_NAME,
    )


@mcp.tool(
    description="Crea una GitHub Discussion in una categoria del repository.",
    structured_output=True,
)
def github_create_discussion(
    repo_full_name: str, category_name: str, title: str, body: str
) -> dict[str, Any]:
    """Crea una nuova discussion in una categoria."""
    return guard_timed(
        create_discussion_impl,
        "github_create_discussion",
        repo_full_name,
        category_name,
        title,
        body,
        logger_name=SERVER_NAME,
    )


@mcp.tool(
    description="Aggiunge un commento top-level a una GitHub Discussion.",
    structured_output=True,
)
def github_add_discussion_comment(repo_full_name: str, number: int, body: str) -> dict[str, Any]:
    """Aggiunge un commento top-level a una discussion."""
    return guard_timed(
        add_discussion_comment_impl,
        "github_add_discussion_comment",
        repo_full_name,
        number,
        body,
        logger_name=SERVER_NAME,
    )


if __name__ == "__main__":
    mcp.run()
