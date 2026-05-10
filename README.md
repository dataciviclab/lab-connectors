# lab-connectors

Package Python condiviso per i repo del DataCivicLab.

Contiene infrastruttura riusata da piu repo: HTTP client e MCP server core.

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

## Installazione

```bash
# Solo HTTP client
pip install lab-connectors

# Con MCP core
pip install lab-connectors[mcp]

# Sviluppo locale
pip install -e ".[dev]"
pip install -e ".[dev,mcp]"  # con tutto
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
