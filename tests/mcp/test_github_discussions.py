"""Tests per github-discussions MCP server.

Usa monkeypatch su _graphql per evitare chiamate HTTP reali.
Smoke test sulla registrazione tool FastMCP.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

# Add server dir to path so imports from server + client work
SERVER_DIR = Path(__file__).resolve().parents[2] / "mcp_servers" / "github-discussions"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from github_discussions_client import (
    _GITHUB_TOKEN_ENV_VARS,
    GitHubDiscussionsClientError,
    _get_token,
    _split_repo,
    add_discussion_comment,
    create_discussion,
    get_discussion,
    get_discussion_comments,
    list_discussions,
    search_discussions,
)

try:
    from server import mcp
except Exception:
    mcp = None

# ── fixtures ──────────────────────────────────────────────────────────

_FAKE_DISCUSSION_NODE = {
    "number": 42,
    "title": "Test Discussion",
    "url": "https://github.com/owner/repo/discussions/42",
    "createdAt": "2026-01-15T10:00:00Z",
    "updatedAt": "2026-06-01T12:00:00Z",
    "answerChosenAt": None,
    "closed": True,
    "closedAt": "2026-06-02T15:55:00Z",
    "category": {"name": "Ideas"},
}

_FAKE_DISCUSSION_NODE_OPEN = {
    **_FAKE_DISCUSSION_NODE,
    "closed": False,
    "closedAt": None,
}

_FAKE_LIST_RESPONSE = {
    "data": {
        "repository": {
            "discussions": {
                "totalCount": 1,
                "pageInfo": {
                    "hasNextPage": False,
                    "hasPreviousPage": False,
                    "startCursor": "Y3Vyc29yOnYyOpHOA1",
                    "endCursor": "Y3Vyc29yOnYyOpHOA2",
                },
                "nodes": [_FAKE_DISCUSSION_NODE],
            }
        }
    }
}

_FAKE_SEARCH_RESPONSE = {
    "data": {
        "search": {
            "discussionCount": 1,
            "nodes": [
                {
                    "number": 42,
                    "title": "Test Discussion",
                    "url": "https://github.com/owner/repo/discussions/42",
                    "createdAt": "2026-01-15T10:00:00Z",
                    "updatedAt": "2026-06-01T12:00:00Z",
                    "answerChosenAt": None,
                    "closed": False,
                    "closedAt": None,
                    "category": {"name": "Ideas"},
                    "author": {"login": "testuser"},
                    "labels": {"nodes": [{"name": "bug", "color": "d73a4a"}]},
                }
            ],
        }
    }
}


@pytest.fixture
def mock_graphql(monkeypatch):
    """Fixture che sostituisce _graphql con una funzione controllata.

    Il dict ``calls`` accumula gli argomenti delle chiamate per asserzioni.
    Il dict ``response`` va impostato dal test prima della chiamata.
    """
    calls: list[dict[str, Any]] = []
    current_response: dict[str, Any] = {}

    def fake_graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
        calls.append({"query": query, "variables": dict(variables)})
        if "error" in current_response:
            raise GitHubDiscussionsClientError(current_response["error"])
        return dict(current_response.get("data", {}))

    monkeypatch.setattr("github_discussions_client._graphql", fake_graphql)
    return calls, current_response


# ── _get_token ─────────────────────────────────────────────────────────


@pytest.mark.pure_unit
class TestGetToken:
    """Test fallback chain del token."""

    @pytest.mark.pure_unit
    def test_first_var_used(self, monkeypatch):
        for var in _GITHUB_TOKEN_ENV_VARS:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv(_GITHUB_TOKEN_ENV_VARS[0], "token-a")
        assert _get_token() == "token-a"

    @pytest.mark.pure_unit
    def test_second_var_fallback(self, monkeypatch):
        for var in _GITHUB_TOKEN_ENV_VARS:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv(_GITHUB_TOKEN_ENV_VARS[1], "token-b")
        assert _get_token() == "token-b"

    @pytest.mark.pure_unit
    def test_third_var_fallback(self, monkeypatch):
        for var in _GITHUB_TOKEN_ENV_VARS:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv(_GITHUB_TOKEN_ENV_VARS[2], "token-c")
        assert _get_token() == "token-c"

    @pytest.mark.pure_unit
    def test_raises_when_missing(self, monkeypatch):
        for var in _GITHUB_TOKEN_ENV_VARS:
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(GitHubDiscussionsClientError, match="Nessun token"):
            _get_token()

    @pytest.mark.pure_unit
    def test_precedence_order(self, monkeypatch):
        """Se tutti e tre presenti, prende il primo."""
        for var in _GITHUB_TOKEN_ENV_VARS:
            monkeypatch.setenv(var, f"value-{var}")
        assert _get_token() == f"value-{_GITHUB_TOKEN_ENV_VARS[0]}"


# ── _split_repo ────────────────────────────────────────────────────────


@pytest.mark.pure_unit
class TestSplitRepo:
    @pytest.mark.pure_unit
    def test_valid(self):
        assert _split_repo("owner/repo") == ("owner", "repo")

    @pytest.mark.pure_unit
    def test_valid_with_spaces(self):
        assert _split_repo("  owner/repo  ") == ("owner", "repo")

    @pytest.mark.pure_unit
    def test_invalid_no_slash(self):
        with pytest.raises(GitHubDiscussionsClientError, match="owner/repo"):
            _split_repo("justrepo")

    @pytest.mark.pure_unit
    def test_invalid_empty_owner(self):
        with pytest.raises(GitHubDiscussionsClientError, match="owner/repo"):
            _split_repo("/repo")

    @pytest.mark.pure_unit
    def test_invalid_empty_repo(self):
        with pytest.raises(GitHubDiscussionsClientError, match="owner/repo"):
            _split_repo("owner/")


# ── list_discussions ───────────────────────────────────────────────────


@pytest.mark.adapter
class TestListDiscussions:
    """Test per list_discussions con _graphql mockato."""

    @pytest.mark.adapter
    def test_forward_no_cursor(self, mock_graphql):
        calls, resp = mock_graphql
        resp["data"] = _FAKE_LIST_RESPONSE["data"]

        result = list_discussions("owner/repo")

        assert result["repo_full_name"] == "owner/repo"
        assert result["discussion_count"] == 1
        disc = result["discussions"][0]
        assert disc["number"] == 42
        assert disc["closed"] is True
        assert disc["closed_at"] == "2026-06-02T15:55:00Z"
        assert result["page_info"]["has_next"] is False

        # Verifica che after sia null (nessun cursor passato)
        vars_ = calls[0]["variables"]
        assert vars_["after"] is None
        assert "before" not in vars_ or vars_.get("before") is None
        assert "limit" in vars_

    @pytest.mark.adapter
    def test_forward_with_after_cursor(self, mock_graphql):
        calls, resp = mock_graphql
        resp["data"] = _FAKE_LIST_RESPONSE["data"]

        result = list_discussions("owner/repo", after="Y3Vyc29yOnYyOpHOA2")

        assert result["discussion_count"] == 1
        # Verifica che after sia passato come variabile, non interpolato
        assert calls[0]["variables"]["after"] == "Y3Vyc29yOnYyOpHOA2"
        # La query non deve contenere il valore interpolato
        assert 'after:"Y3Vyc29yOnYyOpHOA2"' not in calls[0]["query"]

    @pytest.mark.adapter
    def test_backward_with_before_cursor(self, mock_graphql):
        calls, resp = mock_graphql
        resp["data"] = _FAKE_LIST_RESPONSE["data"]

        result = list_discussions("owner/repo", before="Y3Vyc29yOnYyOpHOA3")

        assert result["discussion_count"] == 1
        # backward usa last + before
        assert calls[0]["variables"]["before"] == "Y3Vyc29yOnYyOpHOA3"
        assert "last:" in calls[0]["query"]
        assert "first:" not in calls[0]["query"]

    @pytest.mark.adapter
    def test_category_filter_after_pagination(self, mock_graphql):
        """category_name filtra lato client dopo paginazione GitHub.

        Se la pagina contiene discussioni di altre categorie, vengono escluse.
        """
        _calls, resp = mock_graphql
        nodes = [
            {**_FAKE_DISCUSSION_NODE, "number": 1, "category": {"name": "Ideas"}},
            {**_FAKE_DISCUSSION_NODE_OPEN, "number": 2, "category": {"name": "Q&A"}},
            {**_FAKE_DISCUSSION_NODE_OPEN, "number": 3, "category": {"name": "Ideas"}},
        ]
        resp["data"] = {
            "repository": {
                "discussions": {
                    "totalCount": 3,
                    "pageInfo": {
                        "hasNextPage": False,
                        "hasPreviousPage": False,
                        "startCursor": None,
                        "endCursor": None,
                    },
                    "nodes": nodes,
                }
            }
        }

        result = list_discussions("owner/repo", category_name="Ideas")

        assert result["discussion_count"] == 2
        assert result["total_count"] == 3  # globale non filtrato
        assert [d["number"] for d in result["discussions"]] == [1, 3]
        # #1 è closed=True, #3 è closed=False
        assert result["discussions"][0]["closed"] is True
        assert result["discussions"][1]["closed"] is False

    @pytest.mark.adapter
    def test_empty_response(self, mock_graphql):
        _calls, resp = mock_graphql
        resp["data"] = {
            "repository": {"discussions": {"totalCount": 0, "pageInfo": {}, "nodes": []}}
        }

        result = list_discussions("owner/repo")
        assert result["discussion_count"] == 0
        assert result["discussions"] == []

    @pytest.mark.adapter
    def test_error_from_graphql(self, mock_graphql):
        _calls, resp = mock_graphql
        resp["error"] = "NOT_FOUND"

        with pytest.raises(GitHubDiscussionsClientError, match="NOT_FOUND"):
            list_discussions("owner/repo")


# ── search_discussions ─────────────────────────────────────────────────


@pytest.mark.adapter
class TestSearchDiscussions:
    @pytest.mark.adapter
    def test_search_returns_results(self, mock_graphql):
        calls, resp = mock_graphql
        resp["data"] = _FAKE_SEARCH_RESPONSE["data"]

        result = search_discussions("owner/repo", "test query")

        assert result["discussion_count"] == 1
        assert result["results"][0]["number"] == 42
        assert result["results"][0]["author"] == "testuser"
        assert result["results"][0]["closed"] is False
        assert result["results"][0]["closed_at"] is None
        assert result["results"][0]["labels"] == [{"name": "bug", "color": "d73a4a"}]

        # Verifica scope al repository
        assert "repo:owner/repo" in calls[0]["variables"]["query"]

    @pytest.mark.adapter
    def test_empty_query_raises(self, mock_graphql):
        with pytest.raises(GitHubDiscussionsClientError, match="vuota"):
            search_discussions("owner/repo", "")

    @pytest.mark.adapter
    def test_blank_query_raises(self, mock_graphql):
        with pytest.raises(GitHubDiscussionsClientError, match="vuota"):
            search_discussions("owner/repo", "   ")

    @pytest.mark.adapter
    def test_search_limit(self, mock_graphql):
        calls, resp = mock_graphql
        resp["data"] = {"search": {"discussionCount": 0, "nodes": []}}

        search_discussions("owner/repo", "test", limit=5)
        assert calls[0]["variables"]["limit"] == 5

    @pytest.mark.adapter
    def test_search_limit_clamped(self, mock_graphql):
        calls, resp = mock_graphql
        resp["data"] = {"search": {"discussionCount": 0, "nodes": []}}

        search_discussions("owner/repo", "test", limit=999)
        assert calls[0]["variables"]["limit"] == 50  # max cap

    @pytest.mark.adapter
    def test_search_error(self, mock_graphql):
        _calls, resp = mock_graphql
        resp["error"] = "RATE_LIMITED"

        with pytest.raises(GitHubDiscussionsClientError, match="RATE_LIMITED"):
            search_discussions("owner/repo", "test")


# ── get_discussion / get_discussion_comments ───────────────────────────


@pytest.mark.adapter
class TestGetDiscussion:
    @pytest.mark.adapter
    def test_full_mode_returns_body(self, mock_graphql):
        _calls, resp = mock_graphql
        resp["data"] = {
            "repository": {
                "discussion": {
                    **_FAKE_DISCUSSION_NODE,
                    "id": "D_kw123",
                    "body": "Full body text here",
                }
            }
        }

        result = get_discussion("owner/repo", 42, mode="full")
        assert result["body"] == "Full body text here"
        assert result["number"] == 42
        assert result["closed"] is True
        assert result["closed_at"] == "2026-06-02T15:55:00Z"

    @pytest.mark.adapter
    def test_summary_truncates_body(self, mock_graphql):
        _calls, resp = mock_graphql
        resp["data"] = {
            "repository": {
                "discussion": {
                    **_FAKE_DISCUSSION_NODE,
                    "id": "D_kw123",
                    "body": "A" * 1000,
                }
            }
        }

        result = get_discussion("owner/repo", 42, mode="summary", excerpt_chars=100)
        assert "body" not in result
        assert "body_excerpt" in result
        assert len(result["body_excerpt"]) <= 100 + 3  # + ... troncatura


@pytest.mark.adapter
class TestGetDiscussionComments:
    @pytest.mark.adapter
    def test_returns_comments(self, mock_graphql):
        _calls, resp = mock_graphql
        resp["data"] = {
            "repository": {
                "discussion": {
                    "comments": {
                        "totalCount": 1,
                        "nodes": [
                            {
                                "id": "DC_kw123",
                                "body": "A comment",
                                "createdAt": "2026-01-15T10:00:00Z",
                                "author": {"login": "user1"},
                                "replies": {
                                    "totalCount": 0,
                                    "nodes": [],
                                },
                            }
                        ],
                    }
                }
            }
        }

        result = get_discussion_comments("owner/repo", 42)
        assert result["comment_count"] == 1
        assert result["comments"][0]["author"] == "user1"
        assert result["comments"][0]["body"] == "A comment"


# ── FastMCP tool registration ──────────────────────────────────────────


@pytest.mark.contract
class TestToolRegistration:
    """Smoke test: tutti i tool sono registrati su FastMCP."""

    @pytest.mark.contract
    @pytest.mark.skipif(mcp is None, reason="MCP server not available")
    def test_all_tools_registered(self):
        tools = asyncio.run(mcp.list_tools())
        names = sorted(t.name for t in tools)

        # Tutti i tool esposti dal server
        expected = sorted(
            [
                "github_list_discussions",
                "github_get_discussion",
                "github_get_discussion_summary",
                "github_get_discussion_comments",
                "github_search_discussions",
                "github_create_discussion",
                "github_add_discussion_comment",
            ]
        )
        assert names == expected, f"Mismatch: {names} vs {expected}"


# ── create_discussion / add_discussion_comment ─────────────────────────


@pytest.mark.adapter
class TestCreateDiscussion:
    @pytest.mark.adapter
    def test_requires_non_empty_fields(self, mock_graphql):
        with pytest.raises(GitHubDiscussionsClientError, match="vuoto"):
            create_discussion("owner/repo", "", "title", "body")
        with pytest.raises(GitHubDiscussionsClientError, match="vuoto"):
            create_discussion("owner/repo", "cat", "", "body")
        with pytest.raises(GitHubDiscussionsClientError, match="vuoto"):
            create_discussion("owner/repo", "cat", "title", "")


@pytest.mark.adapter
class TestAddComment:
    @pytest.mark.adapter
    def test_requires_non_empty_body(self, mock_graphql):
        with pytest.raises(GitHubDiscussionsClientError, match="vuoto"):
            add_discussion_comment("owner/repo", 42, "")

    @pytest.mark.adapter
    def test_requires_valid_repo(self, mock_graphql):
        with pytest.raises(GitHubDiscussionsClientError, match="owner/repo"):
            add_discussion_comment("invalid", 42, "body")
