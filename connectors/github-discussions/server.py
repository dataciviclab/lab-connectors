from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from github_discussions_client import (
    GitHubDiscussionsClientError,
    add_discussion_comment as add_discussion_comment_impl,
    create_discussion as create_discussion_impl,
    get_discussion as get_discussion_impl,
    get_discussion_summary as get_discussion_summary_impl,
    get_discussion_comments as get_discussion_comments_impl,
    list_discussions as list_discussions_impl,
)

try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "_local" / "mcp"))
    from mcp_telemetry import mcp_telemetry
except Exception:
    def mcp_telemetry(_connector_name: str):
        def decorator(fn):
            return fn

        return decorator


mcp = FastMCP(
    name="github-discussions",
    instructions=(
        "Connector MCP minimale per GitHub Discussions via GraphQL. "
        "Usalo per leggere, creare discussion e aggiungere commenti top-level."
    ),
)


def _guard(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        return fn(*args, **kwargs)
    except GitHubDiscussionsClientError as exc:
        return {"error": str(exc)}


@mcp.tool(
    description="Elenca le GitHub Discussions di un repository, opzionalmente filtrate per categoria.",
    structured_output=True,
)
@mcp_telemetry("github-discussions")
def github_list_discussions(
    repo_full_name: str, category_name: str | None = None, limit: int = 10
) -> dict[str, Any]:
    return _guard(list_discussions_impl, repo_full_name, category_name, limit)


@mcp.tool(
    description=(
        "Restituisce una GitHub Discussion. "
        "mode=summary restituisce solo un estratto del body (default excerpt_chars=500). "
        "mode=full restituisce il body intero (default, backward compat)."
    ),
    structured_output=True,
)
@mcp_telemetry("github-discussions")
def github_get_discussion(
    repo_full_name: str, number: int, mode: str = "full", excerpt_chars: int = 500
) -> dict[str, Any]:
    return _guard(get_discussion_impl, repo_full_name, number, mode, excerpt_chars)


@mcp.tool(
    description="Restituisce un riepilogo corto di una GitHub Discussion.",
    structured_output=True,
)
@mcp_telemetry("github-discussions")
def github_get_discussion_summary(
    repo_full_name: str, number: int, excerpt_chars: int = 280
) -> dict[str, Any]:
    return _guard(get_discussion_summary_impl, repo_full_name, number, excerpt_chars)


@mcp.tool(
    description=(
        "Restituisce commenti top-level e reply annidate di una GitHub Discussion. "
        "mode=summary tronca body a excerpt_chars (default 200). "
        "mode=full restituisce body interi (default, backward compat)."
    ),
    structured_output=True,
)
@mcp_telemetry("github-discussions")
def github_get_discussion_comments(
    repo_full_name: str,
    number: int,
    limit: int = 20,
    mode: str = "full",
    excerpt_chars: int = 200,
) -> dict[str, Any]:
    return _guard(
        get_discussion_comments_impl, repo_full_name, number, limit, mode, excerpt_chars
    )


@mcp.tool(
    description="Crea una GitHub Discussion in una categoria del repository.",
    structured_output=True,
)
@mcp_telemetry("github-discussions")
def github_create_discussion(
    repo_full_name: str, category_name: str, title: str, body: str
) -> dict[str, Any]:
    return _guard(create_discussion_impl, repo_full_name, category_name, title, body)


@mcp.tool(
    description="Aggiunge un commento top-level a una GitHub Discussion.",
    structured_output=True,
)
@mcp_telemetry("github-discussions")
def github_add_discussion_comment(
    repo_full_name: str, number: int, body: str
) -> dict[str, Any]:
    return _guard(add_discussion_comment_impl, repo_full_name, number, body)


if __name__ == "__main__":
    mcp.run()
