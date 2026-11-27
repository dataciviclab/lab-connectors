"""Test per lab_connectors.gcs.fetch_once — cache per generation.

Il contratto che conta: la seconda chiamata sullo stesso oggetto **non scarica
niente**; una generation nuova scarica in un file nuovo (mai riuso di dati
stantii).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lab_connectors.gcs import fetch_once as mod
from lab_connectors.gcs.fetch_once import (
    FetchResult,
    fetch_once,
    gcs_target,
)

pytestmark = pytest.mark.contract

URL = "https://storage.googleapis.com/bucket/ds/2026/file_2026_clean.parquet"
BODY = b"PAR1" + b"\x00" * 1024


class _Resp:
    def __init__(self, body: bytes = b"", status: int = 200) -> None:
        self._body = body
        self.status_code = status
        self.headers: dict[str, str] = {}

    def iter_content(self, chunk_size: int = 65536) -> list[bytes]:
        return [self._body[i : i + chunk_size] for i in range(0, len(self._body), chunk_size)]


class _Result:
    def __init__(self, response: _Resp | None, err: object = None) -> None:
        self.response = response
        self.err = err


class _FakeClient:
    """Client finto: conta i GET, la generation è gestita a parte."""

    gets = 0
    body: bytes = BODY

    def __init__(self, timeout: int = 0, max_retries: int = 0) -> None:
        self.timeout = timeout

    def get(self, url: str, **kwargs: object) -> _Result:
        type(self).gets += 1
        return _Result(_Resp(type(self).body))


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> type[_FakeClient]:
    _FakeClient.gets = 0
    _FakeClient.body = BODY
    monkeypatch.setattr(mod, "HttpClient", _FakeClient)
    monkeypatch.setattr(mod, "_generation", lambda bucket, key: "123")
    return _FakeClient


def test_gcs_target_accetta_gs_e_https() -> None:
    assert gcs_target("gs://b/k/f.parquet") == ("b", "k/f.parquet")
    assert gcs_target(URL) == ("bucket", "ds/2026/file_2026_clean.parquet")
    assert gcs_target("https://raw.githubusercontent.com/x/y/z.parquet") is None


def test_prima_volta_scarica(fake: type[_FakeClient], tmp_path: Path) -> None:
    res = fetch_once(URL, tmp_path)

    assert isinstance(res, FetchResult)
    assert res.cached is False
    assert res.bytes == len(BODY)
    assert res.path.is_file() and res.path.read_bytes() == BODY
    assert fake.gets == 1


def test_seconda_volta_zero_byte(fake: type[_FakeClient], tmp_path: Path) -> None:
    """Il contratto: stessa generation → nessun GET, zero byte."""
    fetch_once(URL, tmp_path)

    res = fetch_once(URL, tmp_path)

    assert res.cached is True
    assert res.bytes == 0
    assert fake.gets == 1  # nessun secondo download


def test_generation_nuova_download_nuovo(
    fake: type[_FakeClient], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Oggetto riscritto: file nuovo, mai riuso del vecchio contenuto."""
    monkeypatch.setattr(mod, "_generation", lambda bucket, key: "111")
    fake.body = b"OLD"
    first = fetch_once(URL, tmp_path)

    monkeypatch.setattr(mod, "_generation", lambda bucket, key: "222")
    fake.body = b"NEW"
    second = fetch_once(URL, tmp_path)

    assert first.path != second.path
    assert second.path.read_bytes() == b"NEW"
    assert second.cached is False


def test_refresh_forza_download(fake: type[_FakeClient], tmp_path: Path) -> None:
    fetch_once(URL, tmp_path)

    res = fetch_once(URL, tmp_path, refresh=True)

    assert res.cached is False
    assert fake.gets == 2


def test_non_lascia_file_temporanei(fake: type[_FakeClient], tmp_path: Path) -> None:
    fetch_once(URL, tmp_path)

    assert not list(tmp_path.rglob("*.part"))


def test_url_non_gcs_solleva(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non è un oggetto GCS"):
        fetch_once("https://example.org/file.parquet", tmp_path)


def test_oggetto_assente(
    fake: type[_FakeClient], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mod, "_generation", lambda bucket, key: None)

    with pytest.raises(OSError, match="generation"):
        fetch_once(URL, tmp_path)


def test_cache_dir_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DCL_EXTERNAL_CACHE", "off")
    assert mod.cache_dir_from_env(tmp_path) is None
    monkeypatch.setenv("DCL_EXTERNAL_CACHE", str(tmp_path / "cache"))
    assert mod.cache_dir_from_env(None) == tmp_path / "cache"
    monkeypatch.delenv("DCL_EXTERNAL_CACHE")
    assert mod.cache_dir_from_env(tmp_path) == tmp_path
    # Senza default e senza env: directory utente condivisa, non None.
    assert mod.cache_dir_from_env(None) == mod.default_cache_dir()


def test_default_cache_dir_fuori_dal_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DCL_EXTERNAL_CACHE", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert mod.default_cache_dir() == tmp_path / "dcl-external"


def test_gc_rimuove_vecchi(fake: type[_FakeClient], tmp_path: Path) -> None:
    res = fetch_once(URL, tmp_path)

    import os
    import time

    old = time.time() - 100 * 86400
    os.utime(res.path, (old, old))

    assert mod.gc(tmp_path, keep_days=90) == 1
    assert not res.path.exists()


def test_cache_hit_rinfresca_mtime(fake: type[_FakeClient], tmp_path: Path) -> None:
    """Su mount `noatime` serve il mtime: un hit deve aggiornarlo, o `gc`
    cancellerebbe file usati ogni giorno."""
    import os
    import time

    res = fetch_once(URL, tmp_path)
    old = time.time() - 100 * 86400
    os.utime(res.path, (old, old))

    fetch_once(URL, tmp_path)

    assert res.path.stat().st_mtime > old + 86400


def test_cache_spenta_in_ci_per_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Su un runner la cache non riusa nulla: il default non deve penalizzare.

    Scaricare il file intero invece delle colonne usate peggiora l'egress se
    tra un run e l'altro il disco è nuovo. Chi vuole la cache in CI la abilita.
    """
    monkeypatch.delenv("DCL_EXTERNAL_CACHE", raising=False)
    monkeypatch.setenv("CI", "true")
    assert mod.cache_dir_from_env() is None

    monkeypatch.setenv("DCL_EXTERNAL_CACHE", "/tmp/cache")
    assert mod.cache_dir_from_env() == Path("/tmp/cache")
