"""Contratto di errore dei layer HTTP di gcs/manifest.

I test esistenti coprono il parsing (mockando i seam). Questi coprono il
mapping degli errori introdotto quando i moduli sono passati a HttpClient:
status >= 400, timeout, payload non valido.
"""

from __future__ import annotations

import pytest

from lab_connectors.gcs import client as gcs_client
from lab_connectors.gcs import manifest as gcs_manifest
from lab_connectors.http import HttpResult
from lab_connectors.testing import fake_response

pytestmark = pytest.mark.contract


class _FakeClient:
    def __init__(self, result: HttpResult | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.calls: list[tuple[str, str]] = []

    def get(self, url: str) -> HttpResult:
        self.calls.append(("GET", url))
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result

    def head(self, url: str) -> HttpResult:
        self.calls.append(("HEAD", url))
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def _patch_client(monkeypatch: pytest.MonkeyPatch, fake: _FakeClient) -> None:
    monkeypatch.setattr("lab_connectors.http.HttpClient", lambda *a, **k: fake)


class TestHttpGetJsonContract:
    def test_dict_valido(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeClient(
            HttpResult(response=fake_response(200, json_data={"items": []}), err=None)
        )
        _patch_client(monkeypatch, fake)

        assert gcs_client._http_get_json("https://example.test/list") == {"items": []}
        assert fake.calls == [("GET", "https://example.test/list")]

    def test_status_403_solleva_runtime_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeClient(HttpResult(response=fake_response(403, text="forbidden"), err=None))
        _patch_client(monkeypatch, fake)

        with pytest.raises(RuntimeError, match="403"):
            gcs_client._http_get_json("https://example.test/list")

    def test_payload_non_dict_solleva_type_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeClient(HttpResult(response=fake_response(200, json_data=["a", "b"]), err=None))
        _patch_client(monkeypatch, fake)

        with pytest.raises(TypeError, match="non oggetto JSON"):
            gcs_client._http_get_json("https://example.test/list")

    def test_nessuna_risposta_solleva_runtime_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeClient(HttpResult(response=None, err=RuntimeError("dns")))
        _patch_client(monkeypatch, fake)

        with pytest.raises(RuntimeError, match="no response"):
            gcs_client._http_get_json("https://example.test/list")


class TestHttpHeadContract:
    def test_status_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeClient(HttpResult(response=fake_response(200), err=None))
        _patch_client(monkeypatch, fake)

        assert gcs_client._http_head("https://example.test/object") == 200

    def test_nessuna_risposta_ritorna_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeClient(HttpResult(response=None, err=RuntimeError("boom")))
        _patch_client(monkeypatch, fake)

        assert gcs_client._http_head("https://example.test/object") is None


class TestManifestFetchContract:
    def test_risposta_500_ritorna_status_e_body(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeClient(HttpResult(response=fake_response(500, text="oops"), err=None))
        _patch_client(monkeypatch, fake)

        assert gcs_manifest._fetch("https://example.test/manifest.json") == (500, "oops")

    def test_timeout_solleva_timeout_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        err = TimeoutError("timed out")
        fake = _FakeClient(HttpResult(response=None, err=err))
        _patch_client(monkeypatch, fake)

        with pytest.raises(TimeoutError, match="Timeout"):
            gcs_manifest._fetch("https://example.test/manifest.json")

    def test_errore_rete_solleva_runtime_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeClient(HttpResult(response=None, err=RuntimeError("dns")))
        _patch_client(monkeypatch, fake)

        with pytest.raises(RuntimeError, match="non raggiungibile"):
            gcs_manifest._fetch("https://example.test/manifest.json")
