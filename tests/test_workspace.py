"""Tests per lab_connectors.workspace."""

from __future__ import annotations

import json
import os

import pytest

from lab_connectors.workspace import (
    detect_local_root,
    find_repo,
    find_repos,
    get_workspace_root,
)

pytestmark = pytest.mark.pure_unit


class TestGetWorkspaceRoot:
    def test_env_var_overrides(self, tmp_path):
        """DCL_WORKSPACE_ROOT env var ha priorità."""
        os.environ["DCL_WORKSPACE_ROOT"] = str(tmp_path)
        try:
            # Reset lru_cache
            get_workspace_root.cache_clear()
            assert get_workspace_root() == tmp_path
        finally:
            del os.environ["DCL_WORKSPACE_ROOT"]
            get_workspace_root.cache_clear()

    def test_finds_toolkit_marker(self, tmp_path):
        """Trova la root cercando toolkit/ directory."""
        (tmp_path / "toolkit").mkdir()
        (tmp_path / "some" / "deep" / "path").mkdir(parents=True)

        os.environ["DCL_WORKSPACE_ROOT"] = str(tmp_path)
        try:
            get_workspace_root.cache_clear()
            assert get_workspace_root() == tmp_path
        finally:
            del os.environ["DCL_WORKSPACE_ROOT"]
            get_workspace_root.cache_clear()


class TestFindRepos:
    def test_finds_flat_repos(self, tmp_path):
        """Trova repo alla radice del workspace."""
        # Create repo structure
        repo1 = tmp_path / "repo-a"
        repo1.mkdir()
        (repo1 / "registry").mkdir()
        (repo1 / "registry" / "registry.json").write_text(json.dumps({"repo": "repo-a"}))

        repo2 = tmp_path / "repo-b"
        repo2.mkdir()
        (repo2 / "registry").mkdir()
        (repo2 / "registry" / "registry.json").write_text(json.dumps({"repo": "repo-b"}))

        os.environ["DCL_WORKSPACE_ROOT"] = str(tmp_path)
        try:
            find_repos.cache_clear()
            repos = find_repos(tmp_path)
            assert "repo-a" in repos
            assert "repo-b" in repos
            assert repos["repo-a"] == repo1
        finally:
            del os.environ["DCL_WORKSPACE_ROOT"]
            find_repos.cache_clear()

    def test_finds_nested_repos(self, tmp_path):
        """Trova repo in sottocartelle."""
        # Create nested repo
        nested = tmp_path / "incubation" / "my-repo"
        nested.mkdir(parents=True)
        (nested / "registry").mkdir()
        (nested / "registry" / "registry.json").write_text(json.dumps({"repo": "my-repo"}))

        os.environ["DCL_WORKSPACE_ROOT"] = str(tmp_path)
        try:
            find_repos.cache_clear()
            repos = find_repos(tmp_path)
            assert "my-repo" in repos
            assert repos["my-repo"] == nested
        finally:
            del os.environ["DCL_WORKSPACE_ROOT"]
            find_repos.cache_clear()

    def test_skips_hidden_dirs(self, tmp_path):
        """Salta directory nascoste."""
        hidden = tmp_path / ".hidden-repo"
        hidden.mkdir()
        (hidden / "registry").mkdir()
        (hidden / "registry" / "registry.json").write_text(json.dumps({"repo": "hidden-repo"}))

        os.environ["DCL_WORKSPACE_ROOT"] = str(tmp_path)
        try:
            find_repos.cache_clear()
            repos = find_repos(tmp_path)
            assert "hidden-repo" not in repos
        finally:
            del os.environ["DCL_WORKSPACE_ROOT"]
            find_repos.cache_clear()

    def test_max_depth(self, tmp_path):
        """Non scende oltre max_depth."""
        deep = tmp_path / "a" / "b" / "c" / "d" / "e"
        deep.mkdir(parents=True)
        (deep / "registry").mkdir()
        (deep / "registry" / "registry.json").write_text(json.dumps({"repo": "deep-repo"}))

        os.environ["DCL_WORKSPACE_ROOT"] = str(tmp_path)
        try:
            find_repos.cache_clear()
            repos = find_repos(tmp_path)
            assert "deep-repo" not in repos  # depth 5 > max_depth 4
        finally:
            del os.environ["DCL_WORKSPACE_ROOT"]
            find_repos.cache_clear()


class TestFindRepo:
    def test_finds_existing_repo(self, tmp_path):
        """Trova un repo per slug."""
        repo = tmp_path / "my-repo"
        repo.mkdir()
        (repo / "registry").mkdir()
        (repo / "registry" / "registry.json").write_text(json.dumps({"repo": "my-repo"}))

        os.environ["DCL_WORKSPACE_ROOT"] = str(tmp_path)
        try:
            find_repos.cache_clear()
            result = find_repo("my-repo", tmp_path)
            assert result == repo
        finally:
            del os.environ["DCL_WORKSPACE_ROOT"]
            find_repos.cache_clear()

    def test_returns_none_for_missing(self, tmp_path):
        """Restituisce None per slug inesistente."""
        os.environ["DCL_WORKSPACE_ROOT"] = str(tmp_path)
        try:
            find_repos.cache_clear()
            result = find_repo("nonexistent", tmp_path)
            assert result is None
        finally:
            del os.environ["DCL_WORKSPACE_ROOT"]
            find_repos.cache_clear()


class TestDetectLocalRoot:
    def test_finds_local_data(self, tmp_path):
        """Trova out/data/ con parquet files."""
        data_dir = tmp_path / "out" / "data"
        data_dir.mkdir(parents=True)
        (data_dir / "test.parquet").touch()

        result = detect_local_root(tmp_path)
        assert result == str(data_dir)

    def test_returns_none_without_parquet(self, tmp_path):
        """Restituisce None se non ci sono parquet."""
        data_dir = tmp_path / "out" / "data"
        data_dir.mkdir(parents=True)

        result = detect_local_root(tmp_path)
        assert result is None

    def test_returns_none_without_out_dir(self, tmp_path):
        """Restituisce None se out/data/ non esiste."""
        result = detect_local_root(tmp_path)
        assert result is None
