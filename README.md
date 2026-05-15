# lab-connectors

Package Python condiviso per i repo del DataCivicLab.

Contiene infrastruttura riusata da piu repo: HTTP client, MCP server core,
client GCS e context manager DuckDB.

---

## Package disponibili

### `lab_connectors.http`

HTTP client con SSL fallback, retry e timeout. Pattern canonico del Lab.

Supporta `get()`, `head()` (con retry) e `post()` (retry opt-in).

```python
from lab_connectors.http import HttpClient, HttpResult

client = HttpClient(timeout=15)

# GET con retry e SSL fallback
result = client.get("https://www.dati.salute.gov.it/sitemap-0.xml")
assert result.is_ok                  # True se usable
assert result.ssl_fallback_used is None  # SSL primario ok

# POST (retry opt-in per idempotenza)
result = client.post("https://example.com/download", data={"id": "123"})
result = client.post("https://example.com/api", json={"query": "..."})
```

---

### `lab_connectors.mcp`

Infrastruttura condivisa per i server MCP del Lab: init, error handling, logging, cache.

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
# → FastMCP gia configurato con logger strutturato
```

#### `guard()` / `guard_timed()` — error handling standard

```python
from lab_connectors.mcp import create_mcp_server, guard, guard_timed
from lab_connectors.mcp.errors import McpError, ErrorCode

mcp = create_mcp_server("toolkit", "...")

@mcp.tool(description="...", structured_output=True)
def inspect_paths(config_path: str) -> dict:
    return guard(_impl, config_path)

@mcp.tool(description="...", structured_output=True)
def list_runs(config_path: str, status: str | None = None) -> dict:
    return guard_timed(_list_runs, "list_runs", config_path, status=status)

def _impl(config_path: str) -> dict:
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

---

### `lab_connectors.gcs`

Client GCS unificato per operazioni di list, upload e verifica. Supporta 3 modalità:

- `auth=None` (default): prova SDK `google.cloud.storage`, fallback HTTP API pubblica
- `auth=True`: richiede SDK autenticato, fallisce con `RuntimeError` se non disponibile
- `auth=False`: solo HTTP API, nessuna dipendenza SDK

```python
from lab_connectors.gcs import list_objects, object_exists, upload_file

# List public bucket (HTTP API)
results = list_objects("dataciviclab-clean", prefix="ispra/", auth=False)

# Check if object exists (HEAD)
exists = object_exists("dataciviclab-clean", "ispra_ru_base/2024/file.parquet")

# Upload (requires auth)
upload_file("/tmp/file.parquet", "dataciviclab-clean", "slug/2024/file.parquet")
```

#### Requisiti

```bash
pip install lab-connectors[gcs]
```

La modalità `auth=False` e `object_exists()` non richiedono il SDK — funzionano con sole librerie stdlib.

---

### `lab_connectors.duckdb`

Context manager per connessioni DuckDB. Elimina il pattern
``duckdb.connect()`` + ``try/finally`` + ``con.close()``.

```python
from lab_connectors.duckdb import safe_connect

with safe_connect(":memory:") as con:
    result = con.execute("SELECT 1 AS x").fetchall()

with safe_connect("data.duckdb", read_only=True) as con:
    rows = con.execute("SELECT * FROM t").fetchall()
```

#### Requisiti

```bash
pip install lab-connectors[duckdb]
```

---

## Installazione

```bash
# Solo HTTP client
pip install lab-connectors

# Con MCP core
pip install lab-connectors[mcp]

# Con DuckDB safe_connect
pip install lab-connectors[duckdb]

# Sviluppo locale (tutto)
pip install -e ".[dev,mcp,gcs,duckdb]"
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
