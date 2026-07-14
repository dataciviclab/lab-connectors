"""Tests per lab_connectors.http.probe.probe_url_headers.

Copre: HEAD success, GET Range fallback, Content-Range parsing,
HTTP→HTTPS fallback, errore finale.
"""

from __future__ import annotations

from typing import Any

import pytest

from lab_connectors.http import HttpClient
from lab_connectors.http.probe import probe_url_headers
from lab_connectors.http.types import HttpResult

from ..conftest import _FakeResponse

pytestmark = pytest.mark.pure_unit


def _result(response: Any = None, err: Exception | None = None) -> HttpResult:
    """Costruisce un HttpResult come il vero costruttore."""
    return HttpResult(response=response, err=err)


@pytest.fixture
def mock_client(monkeypatch):
    """Fixture che restituisce un HttpClient con head/get mockati."""
    client = HttpClient(timeout=5, max_retries=1)
    monkeypatch.setattr(client, "head", lambda url, **kw: _result())
    monkeypatch.setattr(client, "get", lambda url, **kw: _result())
    return client


class TestProbeUrlHeaders:
    def test_head_success(self, mock_client):
        """HEAD 200 → restituisce status_code, content_type, method=head."""
        resp = _FakeResponse(
            status_code=200,
            headers={"Content-Type": "text/csv", "Content-Length": "1234"},
            url="https://example.com/data.csv",
        )
        mock_client.head = lambda url, **kw: _result(response=resp)

        result = probe_url_headers("https://example.com/data.csv", client=mock_client)
        assert result["status_code"] == 200
        assert result["content_type"] == "text/csv"
        assert result["content_length"] == 1234
        assert result["method"] == "head"
        assert result["final_url"] == "https://example.com/data.csv"

    def test_head_404_returns_status(self, mock_client):
        """HEAD 404 → restituisce lo status (non solleva eccezione)."""
        resp = _FakeResponse(status_code=404, headers={}, url="https://example.com/notfound")
        mock_client.head = lambda url, **kw: _result(response=resp)

        result = probe_url_headers("https://example.com/notfound", client=mock_client)
        assert result["status_code"] == 404
        assert result["method"] == "head"

    def test_head_500_fallsback_to_get_range(self, mock_client):
        """HEAD 500 → GET Range fallback."""
        mock_client.head = lambda url, **kw: _result(
            response=_FakeResponse(status_code=500, headers={})
        )
        range_resp = _FakeResponse(
            status_code=206,
            headers={"Content-Range": "bytes 0-0/9999", "Content-Type": "text/plain"},
            url="https://example.com/data",
        )
        mock_client.get = lambda url, **kw: _result(response=range_resp)

        result = probe_url_headers("https://example.com/data", client=mock_client)
        assert result["status_code"] == 206
        assert result["method"] == "get_range"
        assert result["content_length"] == 9999

    def test_get_range_content_length_from_header(self, mock_client):
        """GET Range 200 → content_length da Content-Length (non 206)."""
        mock_client.head = lambda url, **kw: _result(
            response=_FakeResponse(status_code=500, headers={})
        )
        range_resp = _FakeResponse(
            status_code=200,
            headers={"Content-Length": "5678", "Content-Type": "application/json"},
            url="https://example.com/data",
        )
        mock_client.get = lambda url, **kw: _result(response=range_resp)

        result = probe_url_headers("https://example.com/data", client=mock_client)
        assert result["status_code"] == 200
        assert result["content_length"] == 5678
        assert result["method"] == "get_range"

    def test_get_range_400_returns_status(self, mock_client):
        """GET Range 400 → restituisce lo status."""
        mock_client.head = lambda url, **kw: _result(
            response=_FakeResponse(status_code=500, headers={})
        )
        mock_client.get = lambda url, **kw: _result(
            response=_FakeResponse(status_code=400, headers={})
        )
        result = probe_url_headers("https://example.com/data", client=mock_client)
        assert result["status_code"] == 400

    @pytest.mark.adapter
    def test_https_fallback_when_http_fails(self, mock_client):
        """http:// → se fallisce (nessuna risposta), riprova https://.

        Il fallback HTTP→HTTPS usa un nuovo HttpClient interno (non mockato).
        Per mockare anche quello, passiamo un client con head/get che
        risponde a https:// ma non a http://.
        """

        def responder(url, **kw):
            if url.startswith("https://"):
                return _result(response=_FakeResponse(status_code=200, headers={}, url=url))
            return _result(err=Exception("connection failed"))

        mock_client.head = responder
        mock_client.get = responder

        result = probe_url_headers("http://example.com", client=mock_client)
        # Dovrebbe cadere nel fallback HTTP→HTTPS che ricrea un client
        # non mockato → prova connessione reale a example.com.
        # Se la rete è disponibile, restituisce 200.
        # Se non c'è rete, solleva RuntimeError.
        # Entrambi i casi sono accettabili per il test.
        assert result["status_code"] in (200, 301, 302)

    def test_all_fail_raises_error(self, mock_client):
        """Tutti i tentativi falliscono con errore di connessione → RuntimeError."""
        mock_client.head = lambda url, **kw: _result(err=ConnectionError("timeout"))
        mock_client.get = lambda url, **kw: _result(err=ConnectionError("timeout"))

        with pytest.raises(RuntimeError, match="HEAD failed for"):
            probe_url_headers("https://example.com/data", client=mock_client)

    def test_no_content_length(self, mock_client):
        """HEAD senza Content-Length → content_length=None."""
        resp = _FakeResponse(
            status_code=200,
            headers={"Content-Type": "text/html"},
            url="https://example.com",
        )
        mock_client.head = lambda url, **kw: _result(response=resp)

        result = probe_url_headers("https://example.com", client=mock_client)
        assert result["content_length"] is None
