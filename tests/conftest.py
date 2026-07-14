"""
Fixture condivise per i test di lab-connectors.

Centralizza _FakeResponse (duplicato in test_client.py, test_client_get_head.py,
test_client_backoff.py) e fornisce fake_http per test HTTP.
"""

from __future__ import annotations

import pytest


class _FakeResponse:
    """Minimal response stub duck-typing requests.Response properties.

    Usata nei test HTTP al posto di requests.Response reale.
    Centralizzata qui — importala da conftest invece di ridefinirla.
    """

    def __init__(
        self,
        status_code: int = 200,
        content: bytes = b"ok",
        headers: dict[str, str] | None = None,
        url: str = "",
    ) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self.url = url

    def json(self) -> dict:
        import json

        return json.loads(self.content.decode())

    def raise_for_status(self) -> None:
        import requests

        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


@pytest.fixture
def fake_http():
    """Fixture che restituisce un FakeHttpClient pulito.

    Ogni test riceve un'istanza nuova con responses e requests vuoti.
    """
    from lab_connectors.testing import FakeHttpClient

    return FakeHttpClient()
