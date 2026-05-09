"""Artifact resolution unificato: locale / GCS / GitHub.

Strategy pattern controllato da env var ``MCP_ARTIFACT_BACKEND``:

- ``auto`` (default): tenta GCS, fallisce su locale, segnala fallback
- ``gcs``: solo GCS, errore bloccante se non disponibile
- ``local``: solo file locali

Ogni risposta include metadati di provenienza (source, uri, age_hours).
"""

from __future__ import annotations

import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from lab_connectors.mcp.cache import TtlCache
from lab_connectors.mcp.errors import ErrorCode, McpError

ArtifactBackend = Literal["auto", "gcs", "local"]


@dataclass
class ArtifactResult:
    """Risultato della risoluzione di un artifact.

    Contiene sia il path risolto che la provenienza.
    """

    path: Path
    """Path locale al file (reale o temporaneo scaricato da GCS)."""
    source: Literal["gcs", "local_cache"]
    """Da dove è stato risolto l'artifact."""
    uri: str | None = None
    """URI completo (GCS o path assoluto)."""
    age_hours: float | None = None
    """Età del file in ore (None se non determinabile)."""
    stale: bool = False
    """True se age_hours > max_age_hours."""
    fallback_warning: str | None = None
    """Presente se si è usato un fallback (es. GCS fallito → locale)."""
    warning: str | None = None
    """Altri warning (es. stale, permessi)."""

    def to_dict(self) -> dict:
        """Convert in dict con metadati di provenienza."""
        return {
            "path": str(self.path),
            "source": self.source,
            "uri": self.uri,
            "age_hours": self.age_hours,
            "stale": self.stale,
            "warning": self.warning,
            "fallback_warning": self.fallback_warning,
        }


# — Internal helpers —

GCS_PUBLIC_PREFIX = "https://storage.googleapis.com"


def _backend_from_env() -> ArtifactBackend:
    val = os.environ.get("MCP_ARTIFACT_BACKEND", "auto").strip().lower()
    if val in ("auto", "gcs", "local"):
        return val  # type: ignore[return-value]
    return "auto"


def _gcs_http_url(gcs_uri: str) -> str:
    """Convert gs:// in https:// URL pubblico GCS."""
    if gcs_uri.startswith("gs://"):
        return gcs_uri.replace("gs://", f"{GCS_PUBLIC_PREFIX}/", 1)
    return gcs_uri


def _file_age_hours(path: Path) -> float | None:
    """Età del file in ore, o None se il file non esiste."""
    try:
        mtime = path.stat().st_mtime
        return (time.time() - mtime) / 3600
    except OSError:
        return None


class ArtifactResolver:
    """Resolver unificato per artifact MCP.

    Scenario tipico::

        resolver = ArtifactResolver(
            repo_root=Path("source-observatory"),
            gcs_prefix="gs://dataciviclab-clean/catalog_inventory",
        )
        result = resolver.resolve_parquet("source_check_results.parquet")
        # → ArtifactResult(path=PosixPath('/tmp/so_mcp_...'), source='gcs', ...)

    Args:
        repo_root: Path radice del repository (per artifact locali).
        gcs_prefix: Prefisso GCS (es. ``gs://dataciviclab-clean/catalog_inventory``).
        max_age_hours: Soglia di freschezza per local_cache (default 24).
        backend: Forza backend, altrimenti da env ``MCP_ARTIFACT_BACKEND``.

    """

    def __init__(
        self,
        repo_root: str | Path,
        gcs_prefix: str | None = None,
        max_age_hours: int = 24,
        backend: ArtifactBackend | None = None,
        gcs_timeout: int = 30,
    ) -> None:
        """Inizializza il resolver con root, backend e timeout."""
        self._repo_root = Path(repo_root).resolve()
        self._gcs_prefix = gcs_prefix
        self._max_age_hours = max_age_hours
        self._backend = backend or _backend_from_env()
        self._gcs_cache: TtlCache[str, bytes] = TtlCache(ttl_seconds=600)
        self._gcs_timeout = gcs_timeout

    # — Public API —

    def resolve_parquet(
        self,
        relative_path: str,
        gcs_key: str | None = None,
    ) -> ArtifactResult:
        """Risolve un file parquet.

        Args:
            relative_path: Path relativo al repo_root (es. ``data/.../file.parquet``).
            gcs_key: Path nel bucket GCS (es. ``source-check/file.parquet``).
                     Default: same as relative_path.

        """
        return self._resolve(relative_path, gcs_key or relative_path)

    def resolve_json(
        self,
        relative_path: str,
        gcs_key: str | None = None,
    ) -> ArtifactResult:
        """Risolve un file JSON."""
        return self._resolve(relative_path, gcs_key or relative_path)

    def resolve_yaml(
        self,
        relative_path: str,
        gcs_key: str | None = None,
    ) -> ArtifactResult:
        """Risolve un file YAML."""
        return self._resolve(relative_path, gcs_key or relative_path)

    # — Internal —

    def _resolve(self, relative_path: str, gcs_key: str) -> ArtifactResult:
        """Core resolution: tenta GCS → fallisce su locale."""
        local_path = self._repo_root / relative_path

        # Tentativo GCS
        if self._backend != "local" and self._gcs_prefix:
            gcs_uri = f"{self._gcs_prefix}/{gcs_key}"
            try:
                temp = self._download_gcs(gcs_uri)
                age = _file_age_hours(temp)
                return ArtifactResult(
                    path=temp,
                    source="gcs",
                    uri=gcs_uri,
                    age_hours=age,
                    stale=(age is not None and age > self._max_age_hours),
                )
            except McpError:
                if self._backend == "gcs":
                    raise
                # auto: fallisce su locale con warning
                fallback_warning = (
                    f"GCS non disponibile per {gcs_uri}, uso cache locale"
                )
        else:
            fallback_warning = None

        # Fallback locale
        if not local_path.exists():
            prefix = self._gcs_prefix or ""
            gcs_hint = f"{prefix}/{gcs_key}" if self._gcs_prefix else "nessun GCS configurato"
            raise McpError(
                ErrorCode.ARTIFACT_NOT_FOUND,
                f"Artifact non trovato: {local_path} (cercato anche GCS: {gcs_hint})",
            )

        age = _file_age_hours(local_path)
        stale = age is not None and age > self._max_age_hours
        return ArtifactResult(
            path=local_path,
            source="local_cache",
            uri=str(local_path),
            age_hours=age,
            stale=stale,
            fallback_warning=fallback_warning,
            warning="Il dato locale potrebbe non essere aggiornato" if stale else None,
        )

    def _download_gcs(self, gcs_uri: str) -> Path:
        """Scarica da GCS via HTTP pubblico in un file temporaneo.

        Strategy: HTTP pubblico (requests) → gcloud CLI fallback.
        """
        # Controlla cache
        cached = self._gcs_cache.get(gcs_uri)
        if cached is not None:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".parquet")
            tmp.write(cached)
            tmp.close()
            return Path(tmp.name)

        http_url = _gcs_http_url(gcs_uri)

        try:
            import requests
            resp = requests.get(http_url, stream=True, timeout=self._gcs_timeout)
            resp.raise_for_status()
            data = resp.content
        except Exception as http_err:
            # Fallback: gcloud CLI
            try:
                import subprocess
                tmp_raw = tempfile.NamedTemporaryFile(delete=False, suffix=".parquet")
                tmp_raw.close()
                subprocess.run(
                    ["gcloud", "storage", "cp", gcs_uri, tmp_raw.name],
                    capture_output=True,
                    timeout=60,
                    check=True,
                )
                with open(tmp_raw.name, "rb") as f:
                    data = f.read()
            except Exception as cli_err:
                raise McpError(
                    ErrorCode.GCS_UNAVAILABLE,
                    f"Impossibile scaricare {gcs_uri}: "
                    f"HTTP: {http_err}, gcloud: {cli_err}",
                ) from cli_err

        # Scrivi temp file
        suffix = Path(gcs_uri).suffix or ".bin"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(data)
        tmp.close()

        # Popola cache
        self._gcs_cache.set(gcs_uri, data)

        return Path(tmp.name)

    @property
    def backend(self) -> ArtifactBackend:
        """Backend attualmente in uso."""
        return self._backend
