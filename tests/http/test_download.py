"""Tests per lab_connectors.http.download.download().

Copre: download OK, errore HTTP, timeout, URL vuota, proxy da env.
"""

from __future__ import annotations

from typing import Any

import pytest

from lab_connectors.http import download
from lab_connectors.http.types import HttpResult

from ..conftest import _FakeResponse

pytestmark = [pytest.mark.pure_unit, pytest.mark.contract]


def _patch_client(monkeypatch, fake_get) -> None:
    """Sostituisce HttpClient.get con fake."""
    import lab_connectors.http.client as mod

    monkeypatch.setattr(mod.HttpClient, "get", fake_get)


class TestDownload:
    def test_success(self, monkeypatch):
        """Download OK → bytes."""

        def fake_get(self, url, **kw):
            return HttpResult(response=_FakeResponse(status_code=200, content=b"hello"), err=None)

        monkeypatch.setattr("lab_connectors.http.client.HttpClient.get", fake_get)

        data = download("https://example.com/file.csv", timeout=5)
        assert data == b"hello"

    def test_http_error(self, monkeypatch):
        """Download con 404 → RuntimeError."""

        def fake_get(self, url, **kw):
            return HttpResult(response=_FakeResponse(status_code=404, content=b""), err=None)

        monkeypatch.setattr("lab_connectors.http.client.HttpClient.get", fake_get)

        with pytest.raises(RuntimeError, match="Download failed for"):
            download("https://example.com/notfound", timeout=5)

    def test_connection_error(self, monkeypatch):
        """Errore di connessione → RuntimeError."""

        def fake_get(self, url, **kw):
            return HttpResult(response=None, err=ConnectionError("timeout"))

        monkeypatch.setattr("lab_connectors.http.client.HttpClient.get", fake_get)

        with pytest.raises(RuntimeError, match="Download failed for"):
            download("https://example.com/data", timeout=5)

    def test_empty_url(self):
        """URL vuota → ValueError."""
        with pytest.raises(ValueError, match="URL cannot be empty"):
            download("")

    def test_proxy_from_env(self, monkeypatch):
        """BLOCKED_SOURCE_PROXY → passato a HttpClient.get."""
        monkeypatch.setenv("BLOCKED_SOURCE_PROXY", "http://proxy.test:8888")
        passed_kwargs: dict[str, Any] = {}

        def fake_get(self, url, **kw):
            nonlocal passed_kwargs
            passed_kwargs = kw
            return HttpResult(response=_FakeResponse(status_code=200, content=b"ok"), err=None)

        monkeypatch.setattr("lab_connectors.http.client.HttpClient.get", fake_get)

        download("https://example.com/data", timeout=5)
        assert passed_kwargs.get("proxies") == {
            "http": "http://proxy.test:8888",
            "https": "http://proxy.test:8888",
        }

    def test_proxy_disabled(self, monkeypatch):
        """proxy_from_env=False → non passa proxy."""
        monkeypatch.setenv("BLOCKED_SOURCE_PROXY", "http://proxy.test:8888")
        passed_kwargs: dict[str, Any] = {}

        def fake_get(self, url, **kw):
            nonlocal passed_kwargs
            passed_kwargs = kw
            return HttpResult(response=_FakeResponse(status_code=200, content=b"ok"), err=None)

        monkeypatch.setattr("lab_connectors.http.client.HttpClient.get", fake_get)

        download("https://example.com/data", timeout=5, proxy_from_env=False)
        assert "proxies" not in passed_kwargs
