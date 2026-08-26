"""Dataclass che modellano lo schema registry (ADR-001, v1).

Usage::

    from lab_connectors.registry.models import Registry

    reg = Registry.from_dict(data)
    for ds in reg.datasets:
        print(ds.slug, ds.period)
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

    @classmethod
    def from_dict(cls, d: dict) -> Dataset:
        """Parse from dict."""
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
            location=Location.from_dict(d.get("location", {})),
            stage=d.get("stage", ""),
            mart_refs=d.get("mart_refs", []),
        )


@dataclass
class Mart:
    """Tabella mart pubblicata."""

    slug: str = ""
    dataset: str = ""
    table: str = ""
    name: str = ""
    description: str = ""
    location: Location = field(default_factory=Location)
    primary_key: list[str] = field(default_factory=list)
    required_columns: list[str] = field(default_factory=list)
    min_rows: int | None = None
    columns: list[Column] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> Mart:
        """Parse from dict."""
        return cls(
            slug=d.get("slug", ""),
            dataset=d.get("dataset", ""),
            table=d.get("table", ""),
            name=d.get("name", ""),
            description=d.get("description", ""),
            location=Location.from_dict(d.get("location", {})),
            primary_key=d.get("primary_key", []),
            required_columns=d.get("required_columns", []),
            min_rows=d.get("min_rows"),
            columns=[Column.from_dict(c) for c in d.get("columns", [])],
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
        """Parse from dict."""
        return cls(
            run_id=d.get("run_id", ""),
            year=d.get("year"),
            status=d.get("status", ""),
            quality_score=d.get("quality_score", {}),
            output_rows=d.get("output_rows", {}),
            output_bytes=d.get("output_bytes", {}),
            started_at=d.get("started_at", ""),
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
    """Registry completo di un repo."""

    schema_version: int = 1
    repo: str = ""
    source_repo: str = ""
    updated_at: str = ""
    datasets: list[Dataset] = field(default_factory=list)
    marts: list[Mart] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)
    codelists: list = field(default_factory=list)
    entities: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> Registry:
        """Parse from dict."""
        return cls(
            schema_version=d.get("schema_version", 1),
            repo=d.get("repo", ""),
            source_repo=d.get("source_repo", ""),
            updated_at=d.get("updated_at", ""),
            datasets=[Dataset.from_dict(ds) for ds in d.get("datasets", [])],
            marts=[Mart.from_dict(m) for m in d.get("marts", [])],
            signals=[Signal.from_dict(s) for s in d.get("signals", [])],
            codelists=d.get("codelists", []),
            entities=d.get("entities", {}),
        )


__all__ = [
    "Column",
    "Dataset",
    "Location",
    "Mart",
    "Registry",
    "Run",
    "Signal",
]
