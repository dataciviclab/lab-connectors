"""Dataclass che modellano lo schema registry (v1 e v2).

``Registry.from_dict`` è l'unico punto di compatibilità tra le versioni del
contratto: legge sia ``schema_version: 1`` (location scritte voce per voce,
sezione ``signals``) sia ``schema_version: 2`` (contratto ``gcs`` + ``partitions``
+ ``last_run``, senza ``signals``/``entities``) e espone agli consumer la stessa
superficie dataclass. Per v2 le ``location`` sono sintetizzate da
``lab_connectors.registry.locations``.

Usage::

    from lab_connectors.registry.models import Registry

    reg = Registry.from_dict(data)
    for ds in reg.datasets:
        print(ds.slug, ds.period, ds.clean_rows)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Column:
    """Colonna di un dataset."""

    name: str = ""
    type: str = ""
    role: str = ""
    description: str = ""
    semantic_type: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> Column:
        """Parse from dict."""
        return cls(
            name=d.get("name", ""),
            type=d.get("type", ""),
            role=d.get("role", ""),
            description=d.get("description", ""),
            semantic_type=d.get("semantic_type"),
        )


@dataclass
class Location:
    """Posizione di un artifact su GCS."""

    type: str = "gcs"
    path: str = ""
    multi_file: bool = True

    @classmethod
    def from_dict(cls, d: dict) -> Location:
        """Parse from dict."""
        return cls(
            type=d.get("type", "gcs"),
            path=d.get("path", ""),
            multi_file=d.get("multi_file", True),
        )


@dataclass
class Dataset:
    """Dataset singolo del registry."""

    slug: str = ""
    name: str = ""
    description: str = ""
    source: str = ""
    source_id: str = ""
    period: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    category: str = ""
    columns: list[Column] = field(default_factory=list)
    location: Location = field(default_factory=Location)
    stage: str = ""
    mart_refs: list[str] = field(default_factory=list)
    partitions: dict[int, int] = field(default_factory=dict)
    last_run: Run | None = None

    @property
    def years(self) -> list[int]:
        """Chiavi di partizione pubblicate (anno o legislatura), ordinate."""
        return sorted(self.partitions)

    @property
    def clean_rows(self) -> int | None:
        """Righe clean totali (somma delle partizioni); None se non note."""
        if not self.partitions:
            return None
        return sum(self.partitions.values())

    @classmethod
    def from_dict(cls, d: dict) -> Dataset:
        """Parse from dict (v1 o v2)."""
        location = d.get("location")
        if isinstance(location, str):
            location = {"path": location}
        last_run = d.get("last_run")
        return cls(
            slug=d.get("slug", ""),
            name=d.get("name", ""),
            description=d.get("description", ""),
            source=d.get("source", ""),
            source_id=d.get("source_id", ""),
            period=d.get("period", {}),
            tags=d.get("tags", []),
            category=d.get("category", ""),
            columns=[Column.from_dict(c) for c in d.get("columns", [])],
            location=Location.from_dict(location or {}),
            stage=d.get("stage", ""),
            mart_refs=d.get("mart_refs", []),
            partitions={
                int(key): int(value)
                for key, value in (d.get("partitions") or {}).items()
                if str(key).lstrip("-").isdigit() and value is not None
            },
            last_run=Run.from_dict(last_run) if last_run else None,
        )


@dataclass
class Mart:
    """Tabella mart pubblicata."""

    slug: str = ""
    dataset: str = ""
    table: str = ""
    layout: str = "flat"
    year: int | None = None
    location: Location = field(default_factory=Location)
    primary_key: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> Mart:
        """Parse from dict (v1 o v2)."""
        location = d.get("location")
        if isinstance(location, str):
            location = {"path": location}
        return cls(
            slug=d.get("slug", ""),
            dataset=d.get("dataset", ""),
            table=d.get("table", ""),
            layout=d.get("layout", "flat"),
            year=d.get("year"),
            location=Location.from_dict(location or {}),
            primary_key=d.get("primary_key", []),
        )


@dataclass
class Run:
    """Run singolo di un dataset."""

    run_id: str = ""
    year: int | None = None
    status: str = ""
    quality_score: dict = field(default_factory=dict)
    output_rows: dict = field(default_factory=dict)
    output_bytes: dict = field(default_factory=dict)
    started_at: str = ""
    finished_at: str = ""
    updated_at: str = ""
    duration_seconds: float | None = None

    @classmethod
    def from_dict(cls, d: dict) -> Run:
        """Parse from dict.

        Accetta anche il blocco ``last_run`` v2 (``at``/``year``/``status``):
        ``at`` è l'istante di avvio della run, esposto qui come ``started_at``.
        """
        return cls(
            run_id=d.get("run_id", ""),
            year=d.get("year"),
            status=d.get("status", ""),
            quality_score=d.get("quality_score", {}),
            output_rows=d.get("output_rows", {}),
            output_bytes=d.get("output_bytes", {}),
            started_at=d.get("started_at") or d.get("at", ""),
            finished_at=d.get("finished_at", ""),
            updated_at=d.get("updated_at", ""),
            duration_seconds=d.get("duration_seconds"),
        )


@dataclass
class Signal:
    """Segnale di stato di un dataset."""

    id: str = ""
    source_id: str = ""
    status: str = ""
    label: str = ""
    detail: str = ""
    action: str = ""
    run: Run | None = None

    @classmethod
    def from_dict(cls, d: dict) -> Signal:
        """Parse a Signal from a dict."""
        run_data = d.get("run")
        return cls(
            id=d.get("id", ""),
            source_id=d.get("source_id", ""),
            status=d.get("status", ""),
            label=d.get("label", ""),
            detail=d.get("detail", ""),
            action=d.get("action", ""),
            run=Run.from_dict(run_data) if run_data else None,
        )


@dataclass
class Registry:
    """Registry completo di un repo (v1 o v2)."""

    schema_version: int = 1
    repo: str = ""
    source_repo: str = ""
    updated_at: str = ""
    datasets: list[Dataset] = field(default_factory=list)
    marts: list[Mart] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)
    codelists: list = field(default_factory=list)
    entities: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)
    gcs_prefix: str = ""
    clean_layout: str = "year"

    @classmethod
    def from_dict(cls, d: dict) -> Registry:
        """Parse from dict, normalizzando v1 e v2 alla stessa superficie."""
        gcs = d.get("gcs") or {}
        registry = cls(
            schema_version=int(d.get("schema_version") or 1),
            repo=d.get("repo", ""),
            source_repo=d.get("source_repo", ""),
            updated_at=d.get("updated_at", ""),
            datasets=[Dataset.from_dict(ds) for ds in d.get("datasets", [])],
            marts=[Mart.from_dict(m) for m in d.get("marts", [])],
            signals=[Signal.from_dict(s) for s in d.get("signals", [])],
            codelists=d.get("codelists", []),
            entities=d.get("entities", {}),
            checks=d.get("checks", []),
            gcs_prefix=gcs.get("prefix", ""),
            clean_layout=gcs.get("clean", "year"),
        )
        if registry.schema_version >= 2:
            registry._derive_locations()
        return registry

    def _derive_locations(self) -> None:
        """Sintetizza le ``location`` v2 assenti dal contratto ``gcs``."""
        from lab_connectors.registry.locations import clean_location, mart_location

        for ds in self.datasets:
            if ds.location.path or not ds.partitions:
                continue
            location = clean_location(self.gcs_prefix, self.clean_layout, ds.slug, ds.partitions)
            if location:
                ds.location = Location.from_dict(location)
        for mart in self.marts:
            if mart.location.path:
                continue
            mart.location = Location.from_dict(
                mart_location(
                    self.gcs_prefix,
                    mart.dataset,
                    mart.table,
                    mart.layout or "flat",
                    year=mart.year,
                )
            )

    def prefix_for_slug(self, slug: str) -> str:
        """Estrae il GCS prefix da un dataset registrato.

        v2: il prefix è dichiarato una volta sola in ``gcs.prefix``.
        v1 (fallback): è la parte di path tra il bucket e lo slug nella
        ``location.path`` del dataset. Se il dataset non ha ``location.path``
        o il path non contiene uno slug riconoscibile, restituisce ``""``.

        Esempio::

            # location.path = "gs://dataciviclab-clean/appalti_pubblici/anac_bandi_gara/..."
            registry.prefix_for_slug("anac_bandi_gara")
            # → "appalti_pubblici/"

        """
        if self.gcs_prefix:
            return self.gcs_prefix
        for ds in self.datasets:
            if ds.slug != slug:
                continue
            path = ds.location.path
            if not path.startswith("gs://"):
                return ""
            # gs://bucket/prefix/slug/...
            #          ^^^^^^^^^^
            # Trova lo slug nel path e restituisci tutto prima di esso
            marker = f"/{slug}/"
            idx = path.find(marker)
            if idx < 0:
                # prova con il pattern flat: /{slug}_{year}_clean.parquet
                marker = f"/{slug}_"
                idx = path.find(marker)
            if idx < 0:
                return ""
            # bucket name ends at first '/', prefix starts after
            first_slash = path.index("/", 5)  # dopo 'gs://'
            prefix = path[first_slash + 1 : idx + 1]  # +1 per includere il '/'
            return prefix
        return ""


__all__ = [
    "Column",
    "Dataset",
    "Location",
    "Mart",
    "Registry",
    "Run",
    "Signal",
]
