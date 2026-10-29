"""Tests per lab_connectors.duckdb.sql_page — risoluzione dei file clean.

Copre il bug: la pagina SQL ricostruiva i file clean da ``period`` (anni d'imposta)
assumendo che coincidessero con i nomi delle cartelle (anni di presentazione/file).
Per i dataset con offset 1 chiedeva un anno inesistente (404 su tutta la query) e
saltava l'ultimo pubblicato. La risoluzione ora usa ``location.path`` del registry,
che descrive il layout reale (glob espanso via listing del bucket).
"""

from __future__ import annotations

import pytest

from lab_connectors.duckdb import sql_page

pytestmark = pytest.mark.pure_unit


# ── _urls_from_location ───────────────────────────────────────────────


def test_urls_from_location_single_file_nessun_listing() -> None:
    """Path concreto (multi_file: false): nessun glob, nessuna chiamata di rete."""
    url = sql_page._urls_from_location("gs://bucket/prefix/slug/slug_clean.parquet")
    assert url == ["https://storage.googleapis.com/bucket/prefix/slug/slug_clean.parquet"]


def test_urls_from_location_path_non_gs() -> None:
    assert sql_page._urls_from_location("https://example.com/a.parquet") == []
    assert sql_page._urls_from_location("") == []


def test_urls_from_location_espande_il_glob(monkeypatch: pytest.MonkeyPatch) -> None:
    """Il glob viene espanso listando il bucket e filtrando con glob_to_regex."""

    def fake_list_objects(bucket: str, prefix: str = "", **_kwargs: object) -> list[dict]:
        assert bucket == "bucket"
        # il prefisso è tagliato all'ultimo '/' prima del primo '*'
        assert prefix == "prefix/slug/"
        return [
            {"name": "prefix/slug/2024/slug_2024_clean.parquet"},
            {"name": "prefix/slug/2025/slug_2025_clean.parquet"},
            {"name": "prefix/slug/2025/metadata.json"},  # non matcha il glob
            # nome di cartella non-anno: matcha il glob, quindi deve passare
            {"name": "prefix/slug/altro/slug_altro_clean.parquet"},
        ]

    monkeypatch.setattr("lab_connectors.gcs.client.list_objects", fake_list_objects)

    urls = sql_page._urls_from_location("gs://bucket/prefix/slug/*/slug_*_clean.parquet")

    assert urls == [
        "https://storage.googleapis.com/bucket/prefix/slug/2024/slug_2024_clean.parquet",
        "https://storage.googleapis.com/bucket/prefix/slug/2025/slug_2025_clean.parquet",
        "https://storage.googleapis.com/bucket/prefix/slug/altro/slug_altro_clean.parquet",
    ]


def test_urls_from_location_listing_fallito_ritorna_vuoto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Se il listing fallisce si ritorna [] e il chiamante ricade sugli anni."""

    def boom(*_args: object, **_kwargs: object) -> list[dict]:
        raise RuntimeError("rete")

    monkeypatch.setattr("lab_connectors.gcs.client.list_objects", boom)
    assert sql_page._urls_from_location("gs://bucket/prefix/slug/*/slug_*_clean.parquet") == []


# ── _resolve_slug ─────────────────────────────────────────────────────


def test_resolve_slug_usa_location_path_e_ignora_gli_anni(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Con location.path gli anni passati non contano: si leggono i file reali."""

    def fake_list_objects(bucket: str, prefix: str = "", **_kwargs: object) -> list[dict]:
        return [
            {"name": "prefix/slug/2015/slug_2015_clean.parquet"},
            {"name": "prefix/slug/2025/slug_2025_clean.parquet"},
        ]

    monkeypatch.setattr("lab_connectors.gcs.client.list_objects", fake_list_objects)

    urls, cte, info = sql_page._resolve_slug(
        "slug",
        "prefix/",
        list(range(2014, 2025)),  # period: 2014-2024, come nel registry
        location_path="gs://bucket/prefix/slug/*/slug_*_clean.parquet",
    )

    nomi = [u.rsplit("/", 1)[-1] for u in urls]
    assert nomi == ["slug_2015_clean.parquet", "slug_2025_clean.parquet"]
    assert "read_parquet(['" in cte
    assert info["source"] == "location.path"


def test_regression_period_diverso_dalle_cartelle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regressione: period 2014-2024 ma cartelle 2015-2025.

    Prima del fix la pagina chiedeva ``.../2014/slug_2014_clean.parquet`` (404)
    e non leggeva il 2025. Ora legge le cartelle che esistono davvero.
    """

    def fake_list_objects(bucket: str, prefix: str = "", **_kwargs: object) -> list[dict]:
        return [{"name": f"prefix/slug/{y}/slug_{y}_clean.parquet"} for y in range(2015, 2026)]

    monkeypatch.setattr("lab_connectors.gcs.client.list_objects", fake_list_objects)

    urls, _cte, _info = sql_page._resolve_slug(
        "slug",
        "prefix/",
        list(range(2014, 2025)),
        location_path="gs://bucket/prefix/slug/*/slug_*_clean.parquet",
    )

    anni = sorted(int(u.split("/")[-2]) for u in urls)
    assert anni == list(range(2015, 2026))
    assert 2014 not in anni


def test_resolve_slug_fallback_sugli_anni_senza_location() -> None:
    """Senza location.path resta il comportamento storico (retrocompatibile)."""
    urls, _cte, info = sql_page._resolve_slug("slug", "prefix/", [2023, 2024])
    assert [u.rsplit("/", 1)[-1] for u in urls] == [
        "slug_2023_clean.parquet",
        "slug_2024_clean.parquet",
    ]
    assert info["source"] == "period"


def test_resolve_slug_fallback_se_il_glob_non_matcha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """location.path presente ma nessun file: si ricade sugli anni."""
    monkeypatch.setattr(
        "lab_connectors.gcs.client.list_objects",
        lambda *_a, **_k: [{"name": "prefix/slug/altro.txt"}],
    )
    urls, _cte, info = sql_page._resolve_slug(
        "slug",
        "prefix/",
        [2024],
        location_path="gs://bucket/prefix/slug/*/slug_*_clean.parquet",
    )
    assert len(urls) == 1
    assert urls[0].endswith("/2024/slug_2024_clean.parquet")
    assert info["source"] == "period"


def test_cte_singolo_file_e_lista() -> None:
    assert (
        sql_page._cte_from_urls(["https://x/a.parquet"])
        == "SELECT * FROM read_parquet('https://x/a.parquet')"
    )
    assert sql_page._cte_from_urls(["https://x/a.parquet", "https://x/b.parquet"]) == (
        "SELECT * FROM read_parquet(['https://x/a.parquet', 'https://x/b.parquet'])"
    )
