# lab-connectors

Package Python condiviso per i repo del DataCivicLab.

Contiene infrastruttura riusata da più repo: HTTP client, MCP server core, caching e artifact resolution.

---

## Package disponibili

### `lab_connectors.http`

HTTP client con SSL fallback, retry e timeout. Pattern canonico del Lab.

```python
from lab_connectors.http import HttpClient, HttpResult

client = HttpClient(timeout=15)
result = client.get("https://www.dati.salute.gov.it/sitemap-0.xml")

assert result.is_ok                  # True se usable
assert result.ssl_fallback_used is None  # SSL primario ok
# result.ssl_fallback_used == True    # fallback SSL usato
# result.ssl_fallback_used == False   # entrambi falliti
```

---

### `lab_connectors.mcp`

Infrastruttura condivisa per i server MCP del Lab. Sostituisce il boilerplate
che ogni server replicava (FastMCP init, error handling, logging, artifact resolution, cache).

#### Requisiti

```bash
pip install lab-connectors[mcp]
```

#### `create_mcp_server()` — factory server standardizzato

```python
from lab_connectors.mcp import create_mcp_server

mcp = create_mcp_server(
    name="toolkit",
    instructions="Read-only MCP per ispezione pipeline toolkit.",
)
# → FastMCP già configurato con logger strutturato
```

#### `guard()` / `guard_timed()` — error handling standard

```python
from lab_connectors.mcp import create_mcp_server, guard, guard_timed
from lab_connectors.mcp.errors import McpError, ErrorCode

mcp = create_mcp_server("toolkit", "...")

@mcp.tool(description="Path contract risolto.", structured_output=True)
def inspect_paths(config_path: str, year: int = 0) -> dict:
    return guard(_impl, config_path, year or None)

@mcp.tool(description="Lista run records.", structured_output=True)
def list_runs(config_path: str, status: str | None = None) -> dict:
    return guard_timed(_list_runs, "list_runs", config_path, status=status)

def _impl(config_path: str, year: int | None) -> dict:
    if not config_path:
        raise McpError(ErrorCode.INVALID_PARAMS, "config_path obbligatorio")
    return {"result": "..."}
```

`guard()` cattura `McpError` → `{"error": "codice", "message": "..."}`.
`guard_timed()` fa lo stesso + logga durata, tool name e outcome.

#### `McpError` / `ErrorCode` — tassonomia errori

```python
from lab_connectors.mcp.errors import McpError, ErrorCode

raise McpError(ErrorCode.ARTIFACT_NOT_FOUND, "File non trovato")

err = McpError.from_exception(ValueError("bad value"))
assert err.code == ErrorCode.UNEXPECTED
```

22 codici categorizzati: `artifact_*`, `config_*`, `gcs_*`, `query_*`, `cache_*`, `param_*`.

#### `McpLogger` — logging strutturato

```python
from lab_connectors.mcp.logging import get_mcp_logger

logger = get_mcp_logger("source-observatory")
logger.info("so_probe_url", "Probing URL", url="https://...")
logger.warning("so_probe_url", "Timeout", duration_ms=5000)
logger.timed("so_probe_url", "Done", start=time.monotonic())
```

Ogni log include tool name, messaggio e metadati strutturati (duration_ms, error_code, url, ...).
Attivabile via env `DATACIVICLAB_MCP_LOG_LEVEL=DEBUG`.

#### `TtlCache` — cache generica thread-safe

```python
from lab_connectors.mcp.cache import TtlCache

cache: TtlCache[str, list[str]] = TtlCache(ttl_seconds=300)
cache.set("slug-2024", ["gs://.../file1.parquet"])
urls = cache.get("slug-2024")     # None se scaduto
cache.invalidate("slug-2024")
stats = cache.stats               # entries, oldest_age, ttl
```

#### `ArtifactResolver` — path resolution unificato

Risolve artifact locali e GCS con strategy pattern (auto/gcs/local) e freshness check.

```python
from lab_connectors.mcp.artifact import ArtifactResolver

resolver = ArtifactResolver(
    repo_root=Path("source-observatory"),
    gcs_prefix="gs://dataciviclab-clean/catalog_inventory",
)

result = resolver.resolve_parquet(
    "catalog_inventory/generated/source_check_results.parquet",
    gcs_key="source-check/source_check_results.parquet",
)
# result.path  → /tmp/so_mcp_xxx.parquet (scaricato da GCS)
# result.source → "gcs"
# result.age_hours → 3.5
# result.stale → False
# result.to_dict() → dict con metadati provenienza
```

**Backend** controllato da env `MCP_ARTIFACT_BACKEND`:
- `auto` (default): tenta GCS, fallisce su locale, segnala fallback
- `gcs`: solo GCS, errore bloccante se non disponibile
- `local`: solo file locali

---

## Installazione

```bash
# Solo HTTP client
pip install lab-connectors

# Con MCP core
pip install lab-connectors[mcp]

# Sviluppo locale
pip install -e ".[dev]"

# Sviluppo locale con tutto
pip install -e ".[dev,mcp]"
```

## Test

```bash
pytest tests/
ruff check lab_connectors/
mypy lab_connectors/
```

---

## Cosa NON sta qui

- workflow canonici di pipeline (stanno in `toolkit`)
- skill e playbook (stanno in `lab-ops`)
- logica core di dataset (stanno nei repo dominio)
- tool MCP di dominio specifici (stanno nei rispettivi repo)
