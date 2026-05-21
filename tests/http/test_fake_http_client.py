"""Tests for FakeHttpClient — always runs in CI (no SMOKE_TESTS needed).

Protected contract:
- ``FakeHttpClient`` mirrors ``HttpClient`` interface (get/head/post)
- ``fake_response()`` produces stubs compatible with ``HttpResult``
- Callable response resolver for dynamic responses
- Request log accessible via ``.requests``
"""
from __future__ import annotations

import pytest

from lab_connectors.http import HttpResult
from lab_connectors.testing import FakeHttpClient, fake_response

pytestmark = pytest.mark.contract


class TestRequestMatching:
    """contract: FakeHttpClient.get/head/post match by URL."""

    @pytest.mark.parametrize("method", ["get", "head", "post"])
    def test_method_returns_registered_response(self, method):
        """GET, HEAD, POST restituiscono l'HttpResult registrato per quell'URL."""
        fake = FakeHttpClient()
        url = "https://example.test/resource"
        fake.responses[url] = HttpResult(
            response=fake_response(200, text="ok"), err=None,
        )
        result = getattr(fake, method)(url)
        assert result.is_ok
        assert result.response is not None
        assert result.response.text == "ok"

    def test_connection_error_response(self):
        """HttpResult con err → result.is_error."""
        fake = FakeHttpClient()
        fake.responses["https://example.test/fail"] = HttpResult(
            response=None, err=ConnectionError("refused"),
        )
        result = fake.get("https://example.test/fail")
        assert result.is_error
        assert "refused" in str(result.err)

    def test_ssl_fallback_flag_preserved(self):
        """ssl_fallback_used viene propagato attraverso il fake."""
        fake = FakeHttpClient()
        fake.responses["https://example.test/ssl"] = HttpResult(
            response=fake_response(200), err=None, ssl_fallback_used=True,
        )
        result = fake.get("https://example.test/ssl")
        assert result.ssl_fallback_used is True

    def test_missing_url_raises_keyerror(self):
        """URL non registrato → KeyError con messaggio esplicativo."""
        fake = FakeHttpClient()
        fake.responses["https://example.test/existing"] = HttpResult(
            response=fake_response(200), err=None,
        )
        with pytest.raises(KeyError, match="No response registered"):
            fake.get("https://example.test/missing")

    def test_callable_resolver(self):
        """Valore registrato callable → invocato con (url, **kwargs)."""
        fake = FakeHttpClient()
        calls = []

        def resolver(url, **kw):
            calls.append((url, kw))
            return HttpResult(response=fake_response(200, text="dynamic"), err=None)

        fake.responses["https://example.test/dyn"] = resolver
        result = fake.get("https://example.test/dyn", custom="arg")

        assert result.response.text == "dynamic"  # type: ignore[union-attr]
        assert len(calls) == 1
        assert calls[0][1]["custom"] == "arg"

    def test_request_log(self):
        """Ogni richiesta viene tracciata come (method, url, kwargs)."""
        fake = FakeHttpClient()
        url = "https://example.test/log"
        fake.responses[url] = HttpResult(response=fake_response(200), err=None)
        fake.get(url)
        fake.post(url, data="x")
        assert len(fake.requests) == 2
        assert fake.requests[0] == ("GET", url, {})
        assert fake.requests[1][0] == "POST"


class TestFakeResponseFactory:
    """contract: fake_response() produce stub compatibili con requests.Response."""

    def test_json_access(self):
        """fake_response con json_data → .json() restituisce il dato."""
        resp = fake_response(200, json_data={"key": "val"})
        assert resp.json() == {"key": "val"}

    def test_content_derived_from_text(self):
        """fake_response text → .text string, .content bytes."""
        resp = fake_response(200, text="payload")
        assert resp.text == "payload"
        assert resp.content == b"payload"

    def test_raise_for_status_on_4xx(self):
        """raise_for_status su 403 solleva requests.HTTPError con response accessibile."""
        import requests
        resp = fake_response(403, text="forbidden")
        with pytest.raises(requests.HTTPError) as exc_info:
            resp.raise_for_status()
        assert exc_info.value.response is resp  # il response è il fake response
