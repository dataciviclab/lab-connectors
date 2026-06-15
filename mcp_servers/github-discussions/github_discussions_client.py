"""Client GraphQL per GitHub Discussions.

Fornisce funzioni pubbliche per list, search, get, create discussion e commenti.
Usa httpx per chiamate autenticate all'API GitHub GraphQL.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

# Load .env from workspace root when this repo is used inside the Lab workspace.
load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)

API_URL = "https://api.github.com/graphql"
TIMEOUT_SECONDS = 20

# Ordine di fallback per il token GitHub — allineato a _local/mcp/github/server.sh
_GITHUB_TOKEN_ENV_VARS = [
    "GITHUB_PERSONAL_ACCESS_TOKEN",
    "GITHUB_TOKEN",
    "GH_TOKEN",
]


class GitHubDiscussionsClientError(RuntimeError):
    """Errore sollevato dal client per input non validi o risposte API errate."""


def _get_token() -> str:
    for var in _GITHUB_TOKEN_ENV_VARS:
        token = os.environ.get(var, "").strip()
        if token:
            return token
    raise GitHubDiscussionsClientError(
        "Nessun token GitHub trovato nell'env del server MCP. "
        f"Cercati: {', '.join(_GITHUB_TOKEN_ENV_VARS)}."
    )


def _split_repo(repo_full_name: str) -> tuple[str, str]:
    text = repo_full_name.strip()
    parts = text.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise GitHubDiscussionsClientError("repo_full_name deve avere formato owner/repo")
    return parts[0], parts[1]


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=TIMEOUT_SECONDS,
        headers={
            "Authorization": f"Bearer {_get_token()}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "DataCivicLab GitHub Discussions MCP",
        },
    )


def _graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    payload = {"query": query, "variables": variables}
    try:
        with _client() as client:
            resp = client.post(API_URL, json=payload)
    except httpx.TimeoutException as exc:
        raise GitHubDiscussionsClientError(
            "Timeout durante chiamata GraphQL GitHub Discussions"
        ) from exc
    except httpx.HTTPError as exc:
        raise GitHubDiscussionsClientError(f"Errore HTTP verso GitHub GraphQL: {exc}") from exc

    try:
        data = resp.json()
    except Exception as exc:
        raise GitHubDiscussionsClientError(
            f"GitHub GraphQL ha risposto con JSON non valido (HTTP {resp.status_code})"
        ) from exc

    if resp.status_code >= 400:
        message = data.get("message") if isinstance(data, dict) else None
        if message:
            raise GitHubDiscussionsClientError(f"GitHub GraphQL HTTP {resp.status_code}: {message}")
        raise GitHubDiscussionsClientError(f"GitHub GraphQL HTTP {resp.status_code}")

    errors = data.get("errors")
    if errors:
        first = errors[0] if isinstance(errors, list) and errors else {}
        message = first.get("message") if isinstance(first, dict) else None
        err_type = first.get("type") if isinstance(first, dict) else None
        err_path = first.get("path") if isinstance(first, dict) else None
        details = message or ""
        if err_type:
            details += f" [type: {err_type}]"
        if err_path:
            details += f" [path: {err_path}]"
        raise GitHubDiscussionsClientError(
            f"GitHub GraphQL error: {details}" if details else "GitHub GraphQL ha restituito errors"
        )

    payload_data = data.get("data")
    if payload_data is None:
        raise GitHubDiscussionsClientError("GitHub GraphQL ha restituito data vuoto")
    return payload_data


def _discussion_node_to_summary(node: dict[str, Any]) -> dict[str, Any]:
    category = node.get("category") or {}
    return {
        "number": node.get("number"),
        "title": node.get("title"),
        "url": node.get("url"),
        "category": category.get("name"),
        "created_at": node.get("createdAt"),
        "updated_at": node.get("updatedAt"),
        "answer_chosen": bool(node.get("answerChosenAt")),
        "closed": bool(node.get("closed")),
        "closed_at": node.get("closedAt"),
    }


def _comment_node_to_dict(
    node: dict[str, Any], max_body_chars: int | None = None
) -> dict[str, Any]:
    replies = ((node.get("replies") or {}).get("nodes")) or []
    body = node.get("body", "")
    return {
        "comment_id": node.get("id"),
        "author": ((node.get("author") or {}).get("login")),
        "body": body if max_body_chars is None else _excerpt(body, max_body_chars),
        "created_at": node.get("createdAt"),
        "reply_count": ((node.get("replies") or {}).get("totalCount")) or 0,
        "replies": [
            {
                "reply_id": reply.get("id"),
                "author": ((reply.get("author") or {}).get("login")),
                "body": reply.get("body", "")
                if max_body_chars is None
                else _excerpt(reply.get("body", ""), max_body_chars),
                "created_at": reply.get("createdAt"),
            }
            for reply in replies
        ],
    }


def _excerpt(text: str, max_chars: int = 280) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "..."


def _get_repository_and_categories(
    repo_full_name: str,
) -> tuple[str, list[dict[str, Any]]]:
    owner, name = _split_repo(repo_full_name)
    query = """
    query($owner:String!, $name:String!) {
      repository(owner:$owner, name:$name) {
        id
        discussionCategories(first:50) {
          nodes {
            id
            name
            isAnswerable
          }
        }
      }
    }
    """
    data = _graphql(query, {"owner": owner, "name": name})
    repo = data.get("repository")
    if not repo:
        raise GitHubDiscussionsClientError(
            f"Repository non trovato o Discussions non disponibili: {repo_full_name}"
        )
    categories = (repo.get("discussionCategories") or {}).get("nodes") or []
    return str(repo.get("id")), categories


def _get_discussion_id(repo_full_name: str, number: int) -> str:
    owner, name = _split_repo(repo_full_name)
    query = """
    query($owner:String!, $name:String!, $number:Int!) {
      repository(owner:$owner, name:$name) {
        discussion(number:$number) {
          id
        }
      }
    }
    """
    data = _graphql(query, {"owner": owner, "name": name, "number": number})
    discussion = ((data.get("repository") or {}).get("discussion")) or None
    if not discussion:
        raise GitHubDiscussionsClientError(f"Discussion #{number} non trovata in {repo_full_name}")
    return str(discussion.get("id"))


def search_discussions(repo_full_name: str, query: str, limit: int = 10) -> dict[str, Any]:
    """Cerca discussions in un repository per testo libero.

    Usa la GitHub GraphQL Search API (type: DISCUSSION) per full-text search
    su titolo, body e commenti. Limita i risultati al repository specificato.
    """
    if not query.strip():
        raise GitHubDiscussionsClientError("query di ricerca vuota")

    owner, name = _split_repo(repo_full_name)
    safe_limit = max(1, min(limit, 50))
    search_query = f"repo:{owner}/{name} {query.strip()}"

    q = """
    query($query:String!, $limit:Int!) {
      search(query:$query, type:DISCUSSION, first:$limit) {
        discussionCount
        nodes {
          ... on Discussion {
            number
            title
            url
            createdAt
            updatedAt
            answerChosenAt
            closed
            closedAt
            category { name }
            author { login }
            labels(first:10) {
              nodes { name color }
            }
          }
        }
      }
    }
    """
    data = _graphql(q, {"query": search_query, "limit": safe_limit})
    search_payload = data.get("search") or {}
    nodes = search_payload.get("nodes") or []
    results = []
    for node in nodes:
        category = node.get("category") or {}
        labels_nodes = ((node.get("labels") or {}).get("nodes")) or []
        results.append(
            {
                "number": node.get("number"),
                "title": node.get("title"),
                "url": node.get("url"),
                "category": category.get("name"),
                "author": ((node.get("author") or {}).get("login")),
                "created_at": node.get("createdAt"),
                "updated_at": node.get("updatedAt"),
                "answer_chosen": bool(node.get("answerChosenAt")),
                "closed": bool(node.get("closed")),
                "closed_at": node.get("closedAt"),
                "labels": [
                    {"name": lbl.get("name"), "color": lbl.get("color")} for lbl in labels_nodes
                ],
            }
        )

    return {
        "repo_full_name": repo_full_name,
        "query": query.strip(),
        "limit": safe_limit,
        "discussion_count": search_payload.get("discussionCount") or len(results),
        "results": results,
    }


def list_discussions(
    repo_full_name: str,
    category_name: str | None = None,
    limit: int = 10,
    after: str | None = None,
    before: str | None = None,
) -> dict[str, Any]:
    """Elenca discussions ordinate per UPDATED_AT discendente.

    Supporta cursor pagination con i parametri ``after`` e ``before``
    (passa il ``cursor`` dalla risposta precedente).

    Nota: il filtro ``category_name`` viene applicato lato client dopo la
    paginazione GitHub. Con paginazione attiva, una pagina può restituire
    ``discussion_count=0`` anche se discussioni della categoria esistono
    più avanti. ``total_count`` è il conteggio globale non filtrato.
    """
    owner, name = _split_repo(repo_full_name)
    safe_limit = max(1, min(limit, 50))

    if before:
        # backward pagination — usa last + before
        query = """
        query($owner:String!, $name:String!, $limit:Int!, $before:String!) {
          repository(owner:$owner, name:$name) {
            discussions(last:$limit, before:$before, orderBy:{field:UPDATED_AT, direction:DESC}) {
              totalCount
              pageInfo { hasNextPage hasPreviousPage startCursor endCursor }
              nodes {
                number title url createdAt updatedAt answerChosenAt closed closedAt
                category { name }
              }
            }
          }
        }
        """
        variables: dict[str, Any] = {
            "owner": owner,
            "name": name,
            "limit": safe_limit,
            "before": before,
        }
    else:
        # forward pagination (default) — usa first + after (after opzionale, null = prima pagina)
        query = """
        query($owner:String!, $name:String!, $limit:Int!, $after:String) {
          repository(owner:$owner, name:$name) {
            discussions(first:$limit, after:$after, orderBy:{field:UPDATED_AT, direction:DESC}) {
              totalCount
              pageInfo { hasNextPage hasPreviousPage startCursor endCursor }
              nodes {
                number title url createdAt updatedAt answerChosenAt closed closedAt
                category { name }
              }
            }
          }
        }
        """
        variables = {
            "owner": owner,
            "name": name,
            "limit": safe_limit,
            "after": after,
        }

    data = _graphql(query, variables)
    discussions_payload = ((data.get("repository") or {}).get("discussions")) or {}
    nodes = discussions_payload.get("nodes") or []
    page_info = discussions_payload.get("pageInfo") or {}
    discussions = [_discussion_node_to_summary(node) for node in nodes]

    if category_name and category_name.strip():
        wanted = category_name.strip().casefold()
        discussions = [
            item for item in discussions if (item.get("category") or "").casefold() == wanted
        ]

    return {
        "repo_full_name": repo_full_name,
        "category_name": category_name,
        "limit": safe_limit,
        "total_count": discussions_payload.get("totalCount") or len(discussions),
        "discussion_count": len(discussions),
        "page_info": {
            "has_next": page_info.get("hasNextPage", False),
            "has_previous": page_info.get("hasPreviousPage", False),
            "start_cursor": page_info.get("startCursor"),
            "end_cursor": page_info.get("endCursor"),
        },
        "discussions": discussions,
    }


def get_discussion(
    repo_full_name: str, number: int, mode: str = "full", excerpt_chars: int = 500
) -> dict[str, Any]:
    """Recupera una discussion per numero con body intero o riepilogo."""
    owner, name = _split_repo(repo_full_name)
    query = """
    query($owner:String!, $name:String!, $number:Int!) {
      repository(owner:$owner, name:$name) {
        discussion(number:$number) {
          id
          number
          title
          url
          body
          createdAt
          updatedAt
          answerChosenAt
          closed
          closedAt
          category { name }
        }
      }
    }
    """
    data = _graphql(query, {"owner": owner, "name": name, "number": number})
    discussion = ((data.get("repository") or {}).get("discussion")) or None
    if not discussion:
        raise GitHubDiscussionsClientError(f"Discussion #{number} non trovata in {repo_full_name}")

    category = discussion.get("category") or {}
    base = {
        "repo_full_name": repo_full_name,
        "discussion_id": discussion.get("id"),
        "number": discussion.get("number"),
        "title": discussion.get("title"),
        "url": discussion.get("url"),
        "category": category.get("name"),
        "created_at": discussion.get("createdAt"),
        "updated_at": discussion.get("updatedAt"),
        "answer_chosen": bool(discussion.get("answerChosenAt")),
        "closed": bool(discussion.get("closed")),
        "closed_at": discussion.get("closedAt"),
        "mode": mode,
    }

    safe_mode = mode if mode in ("full", "summary") else "full"
    safe_excerpt = max(80, min(excerpt_chars, 2000))

    if safe_mode == "summary":
        body_text = discussion.get("body", "")
        base["body_excerpt"] = _excerpt(body_text, safe_excerpt)
        base["body_chars"] = len(body_text) if body_text else 0
        base["excerpt_chars"] = safe_excerpt
        return base

    return {**base, "body": discussion.get("body", "")}


def get_discussion_summary(
    repo_full_name: str, number: int, excerpt_chars: int = 280
) -> dict[str, Any]:
    """Restituisce un riepilogo breve di una discussion."""
    discussion = get_discussion(repo_full_name, number)
    safe_excerpt_chars = max(80, min(excerpt_chars, 600))
    return {
        "repo_full_name": discussion["repo_full_name"],
        "discussion_id": discussion["discussion_id"],
        "number": discussion["number"],
        "title": discussion["title"],
        "url": discussion["url"],
        "category": discussion["category"],
        "created_at": discussion["created_at"],
        "updated_at": discussion["updated_at"],
        "answer_chosen": discussion["answer_chosen"],
        "closed": discussion["closed"],
        "closed_at": discussion["closed_at"],
        "body_excerpt": _excerpt(discussion.get("body", ""), safe_excerpt_chars),
        "excerpt_chars": safe_excerpt_chars,
    }


def get_discussion_comments(
    repo_full_name: str,
    number: int,
    limit: int = 20,
    mode: str = "full",
    excerpt_chars: int = 200,
) -> dict[str, Any]:
    """Recupera commenti e reply annidate di una discussion."""
    owner, name = _split_repo(repo_full_name)
    safe_limit = max(1, min(limit, 50))
    safe_mode = mode if mode in ("full", "summary") else "full"
    safe_excerpt = max(80, min(excerpt_chars, 1000)) if safe_mode == "summary" else None
    query = """
    query($owner:String!, $name:String!, $number:Int!, $limit:Int!) {
      repository(owner:$owner, name:$name) {
        discussion(number:$number) {
          id
          comments(first:$limit) {
            totalCount
            nodes {
              id
              body
              createdAt
              author { login }
              replies(first:10) {
                totalCount
                nodes {
                  id
                  body
                  createdAt
                  author { login }
                }
              }
            }
          }
        }
      }
    }
    """
    data = _graphql(
        query,
        {"owner": owner, "name": name, "number": number, "limit": safe_limit},
    )
    discussion = ((data.get("repository") or {}).get("discussion")) or None
    if not discussion:
        raise GitHubDiscussionsClientError(f"Discussion #{number} non trovata in {repo_full_name}")
    comments_payload = discussion.get("comments") or {}
    nodes = comments_payload.get("nodes") or []
    comments = [_comment_node_to_dict(node, max_body_chars=safe_excerpt) for node in nodes]
    return {
        "repo_full_name": repo_full_name,
        "number": number,
        "limit": safe_limit,
        "mode": safe_mode,
        "comment_count": len(comments),
        "total_comment_count": comments_payload.get("totalCount") or len(comments),
        "comments": comments,
    }


def create_discussion(
    repo_full_name: str, category_name: str, title: str, body: str
) -> dict[str, Any]:
    """Crea una nuova discussion in una categoria del repository."""
    if not category_name.strip():
        raise GitHubDiscussionsClientError("category_name vuoto")
    if not title.strip():
        raise GitHubDiscussionsClientError("title vuoto")
    if not body.strip():
        raise GitHubDiscussionsClientError("body vuoto")

    repo_id, categories = _get_repository_and_categories(repo_full_name)
    wanted = category_name.strip().casefold()
    category = next(
        (item for item in categories if (item.get("name") or "").casefold() == wanted),
        None,
    )
    if not category:
        available = ", ".join(
            sorted(item.get("name", "") for item in categories if item.get("name"))
        )
        raise GitHubDiscussionsClientError(
            f"Categoria '{category_name}' non trovata in {repo_full_name}. "
            f"Categorie disponibili: {available}"
        )

    mutation = """
    mutation($repositoryId:ID!, $categoryId:ID!, $title:String!, $body:String!) {
      createDiscussion(input:{
        repositoryId:$repositoryId,
        categoryId:$categoryId,
        title:$title,
        body:$body
      }) {
        discussion {
          id
          number
          url
        }
      }
    }
    """
    data = _graphql(
        mutation,
        {
            "repositoryId": repo_id,
            "categoryId": str(category.get("id")),
            "title": title.strip(),
            "body": body.strip(),
        },
    )
    discussion = ((data.get("createDiscussion") or {}).get("discussion")) or None
    if not discussion:
        raise GitHubDiscussionsClientError("createDiscussion non ha restituito discussion")
    return {
        "repo_full_name": repo_full_name,
        "number": discussion.get("number"),
        "url": discussion.get("url"),
    }


def add_discussion_comment(repo_full_name: str, number: int, body: str) -> dict[str, Any]:
    """Aggiunge un commento top-level a una discussion."""
    if not body.strip():
        raise GitHubDiscussionsClientError("body vuoto")
    discussion_id = _get_discussion_id(repo_full_name, number)
    mutation = """
    mutation($discussionId:ID!, $body:String!) {
      addDiscussionComment(input:{discussionId:$discussionId, body:$body}) {
        comment {
          id
          url
        }
      }
    }
    """
    data = _graphql(mutation, {"discussionId": discussion_id, "body": body.strip()})
    comment = ((data.get("addDiscussionComment") or {}).get("comment")) or None
    if not comment:
        raise GitHubDiscussionsClientError("addDiscussionComment non ha restituito comment")
    return {
        "repo_full_name": repo_full_name,
        "number": number,
        "comment_id": comment.get("id"),
        "url": comment.get("url"),
    }
