"""Tests per lab_connectors.http.download.download().

Copre: download OK, errore HTTP, errore connessione, URL vuota.
"""

from __future__ import annotations

import pytest

from lab_connectors.http import download
from lab_connectors.http.types import HttpResult

from ..conftest import _FakeResponse

pytestmark = [pytest.mark.pure_unit, pytest.mark.contract]


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
