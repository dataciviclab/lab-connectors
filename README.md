# lab-connectors

Package Python condiviso per i repo del DataCivicLab.

Contiene infrastruttura riusata da piu repo: HTTP client, MCP server core,
client GCS, path contract GCS, context manager DuckDB e utility per test.

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

#### `HttpClient` — parametri principali

| Parametro | Default | Descrizione |
|---|---|---|
| `timeout` | `60` | Timeout in secondi (int o tupla (connect, read)) |
| `max_retries` | `2` | Tentativi massimi (incluso il primo; 2 = 1 tentativo + 1 retry) |
| `retry_backoff` | `1.0` | Base backoff esponenziale: `backoff * 2^(attempt-1)` |
| `retry_jitter` | `0.0` | Fattore di randomizzazione (±jitter%). 0.1 = ±10%. Disabilitato di default |
| `circuit_threshold` | `0` | Errori consecutivi per aprire il circuit breaker per-host (0 = disabilitato) |
| `user_agent` | `DataCivicLab-HttpClient/0.1` | User-Agent per le richieste |

#### `GenericPool` — thread pool per richieste parallele (uso interno)

Wrapper su `concurrent.futures.ThreadPoolExecutor` per eseguire richieste HTTP in parallelo.
**Non esportato dalla superficie pubblica** — non più raccomandato per nuovi consumer.
Usa direttamente `concurrent.futures.ThreadPoolExecutor` con `HttpClient` invece.

#### Client SPARQL

Esecuzione di query SPARQL su endpoint HTTPS, con paginazione automatica e fetch CSV.

```python
from lab_connectors.http.sparql import execute_sparql, discover_graphs

results = execute_sparql(
    "https://semantic.istat.it/sparql",
    "SELECT * WHERE { ?s ?p ?o } LIMIT 10",
)
graphs = discover_graphs("https://semantic.istat.it/sparql")
```

#### Tipi di ritorno

| Tipo | Descrizione |
|---|---|
| `HttpResult` | Risultato HTTP: `response`, `err`, `is_ok`, `ssl_fallback_used` |
| `HttpFallbackError` | Wrapper per errori durante retry/fallback |
| `CircuitOpenError` | Restituito in `HttpResult.err` se il circuit breaker è aperto (troppi errori consecutivi sullo stesso host) |

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

#### GCS client API

```python
from lab_connectors.gcs import list_objects, object_exists, upload_file, upload_string, check_public

# List public bucket (HTTP API)
results = list_objects("dataciviclab-clean", prefix="ispra/", auth=False)

# Check if object exists (HEAD, no SDK needed)
exists = object_exists("dataciviclab-clean", "ispra_ru_base/2024/file.parquet")

# Upload file (requires auth)
upload_file("/tmp/file.parquet", "dataciviclab-clean", "slug/2024/file.parquet")

# Upload string content (requires auth)
upload_string('{"key": "value"}', "dataciviclab-clean", "slug/2024/manifest.json")
```

#### Requisiti

```bash
pip install lab-connectors[gcs]
```

`object_exists()` non richiede il SDK (solo HTTP API). `upload_file()` e `upload_string()` richiedono invece SDK autenticato.

#### Path contract GCS (`lab_connectors.gcs.paths`)

Il modulo `paths` definisce i **path canonici** di tutti gli artifact su GCS del DataCivicLab.
I pattern sono caricati da `paths.json` e coprono 2 bucket e 8 pattern.

**Bucket:**

| Costante | Valore | Uso |
|---|---|---|
| `CLEAN_BUCKET` | `dataciviclab-clean` | Dati puliti (parquet, manifest) |
| `MART_BUCKET` | `dataciviclab-mart` | Dati aggregati (mart parquet) |

**Pattern canonici (tutti risolvibili con `resolve()`):**

| Chiave | Pattern | Parametri |
|---|---|---|
| `clean_parquet` | `{slug}/{year}/{slug}_{year}_clean.parquet` | slug, year |
| `pipeline_run` | `{slug}/{year}/pipeline_run.json` | slug, year |
| `catalog_manifest` | `catalog/manifest.json` | — |
| `catalog_signals` | `catalog/catalog_signals.json` | — |
| `catalog_inventory_latest` | `catalog_inventory/catalog_inventory_latest.parquet` | — |
| `catalog_inventory_report` | `catalog_inventory/catalog_inventory_report.json` | — |
| `catalog_inventory_source_check` | `catalog_inventory/source-check/source_check_results.parquet` | — |
| `mart_parquet` | `{slug}/{year}/{table}.parquet` | slug, year, table |

```python
from lab_connectors.gcs.paths import (
    CLEAN_BUCKET, MART_BUCKET,
    resolve, gs_url, https_url,
    parse_gs_url, glob_to_regex,
    pipeline_run, catalog_manifest, mart_parquet,
)

# Risolvere path relativi
path = resolve("clean_parquet", slug="ispra_ru_base", year=2024)
# → "ispra_ru_base/2024/ispra_ru_base_2024_clean.parquet"

# URL GCS (bucket_key + pattern_key + kwargs del pattern)
gs = gs_url("clean", "clean_parquet", slug="ispra_ru_base", year=2024)
# → "gs://dataciviclab-clean/ispra_ru_base/2024/ispra_ru_base_2024_clean.parquet"

# URL HTTPS pubblico
https = https_url("clean", "clean_parquet", slug="ispra_ru_base", year=2024)
# → "https://storage.googleapis.com/dataciviclab-clean/.../ispra_ru_base_2024_clean.parquet"

# Parsing URL gs:// in (bucket, key)
bucket, key = parse_gs_url("gs://dataciviclab-clean/slug/file.parquet")

# Glob pattern → regex (un argomento)
import re
rx = glob_to_regex("*/2024/*.parquet")
bool(re.match(rx, "slug/2024/data.parquet"))  # True

# Convenience function — restituiscono path relativo (str)
run = pipeline_run(slug="ispra_ru_base", year=2024)
# → "ispra_ru_base/2024/pipeline_run.json"

manifest = catalog_manifest()
# → "catalog/manifest.json"

parquet = mart_parquet(slug="demo", year=2024, table="summary")
# → "demo/2024/summary.parquet"
```

---

### `lab_connectors.duckdb`

Context manager per connessioni DuckDB. Elimina il pattern
``duckdb.connect()`` + ``try/finally`` + ``con.close()``.

```python
from lab_connectors.duckdb import safe_connect

with safe_connect(":memory:") as con:
    result = con.execute("SELECT 1 AS x").fetchall()
```

#### `safe_connect()` — connessione generica

Imposta automaticamente `memory_limit='2GB'` e `PRAGMA disable_progress_bar`.
Supporta estensioni (`httpfs`, `spatial`, ...) e configurazioni custom.

```python
with safe_connect("path/to/db.duckdb", extensions=["httpfs", "spatial"]) as con:
    con.execute("SELECT * FROM spatial_table")
```

#### `gcs_connect()` — connessione ottimizzata per GCS

Wrapper che configura DuckDB per leggere parquet direttamente da GCS
via S3 API gateway (estensione `httpfs` + `GCS_S3_CONFIG`).

```python
from lab_connectors.duckdb import gcs_connect

with gcs_connect("s3://dataciviclab-clean/slug/2024/file.parquet") as con:
    result = con.execute("SELECT count(*) FROM read_parquet(?)", ["s3://..."]).fetchone()
```

#### `GCS_S3_CONFIG` (deprecato)

Dict di configurazione DuckDB per l'interfaccia S3-compatible di GCS.
**Deprecato.** Preferisci `gcs_connect()` con URL HTTPS — DuckDB legge
`https://storage.googleapis.com/...` nativamente senza estensione `httpfs`,
evitando il bug "Information loss on integer cast".

```python
from lab_connectors.duckdb import GCS_S3_CONFIG  # DeprecationWarning
```

#### Requisiti

```bash
pip install lab-connectors[duckdb]
```

---

### `lab_connectors.testing`

Fake HTTP client e utility per test. Sostituisce le chiamate HTTP reali con risposte pre-configurate,
senza monkeypatch o mock artigianali.

```python
from lab_connectors.testing import FakeHttpClient, fake_response
from lab_connectors.http import HttpResult

fake = FakeHttpClient()

# Registra risposta JSON per URL specifico
fake.responses["https://example.com/api/data"] = HttpResult(
    response=fake_response(200, '{"values": [1, 2, 3]}'),
    err=None,
)

# Usa il client normalmente — nessuna HTTP reale
result = fake.get("https://example.com/api/data")
assert result.is_ok
assert result.response.json() == {"values": [1, 2, 3]}

# Ispziona le richieste effettuate
assert ("GET", "https://example.com/api/data", {}) in fake.requests
```

`FakeHttpClient` rispecchia l'interfaccia di `HttpClient` (`.get()`, `.head()`, `.post()`,
`.close()`, context manager) ma non fa rete. Le risposte possono essere valori fissi
o callable `(url, **kwargs) -> HttpResult` per comportamenti dinamici.

#### `fake_response()` — factory per stub `requests.Response`

```python
resp = fake_response(
    status_code=200,
    text='{"ok": true}',
    json_data={"ok": True},       # evita re-parsing JSON
    headers={"Content-Type": "application/json"},
)
# .status_code, .text, .content, .json(), .ok, .headers, .raise_for_status()
# .close() e .iter_content() per compatibilità streaming
```

#### `audit-test-markers` — CLI per audit marker pytest

Disponibile con l'installazione base (dipende solo da stdlib).

```bash
audit-test-markers tests/
```

Analizza i marcatori pytest nei file di test e verifica la copertura
dei marker obbligatori (`pure_unit`, `contract`, `adapter`, `policy`, ecc.).

---

## Installazione

```bash
# Solo HTTP client
pip install lab-connectors

# Con MCP core
pip install lab-connectors[mcp]

# Con DuckDB safe_connect
pip install lab-connectors[duckdb]

# Con GCS
pip install lab-connectors[gcs]

# Con testing utilities (FakeHttpClient, audit CLI — già nel base install)
pip install lab-connectors

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

### Eccezione: `mcp_servers/github-discussions`

Il server MCP per GitHub Discussions (`mcp_servers/github-discussions/`) viola la regola sopra
perché è un server MCP di dominio, non un connector infrastrutturale.

**Perché sta qui**: `lab-connectors` è l'unico repo garantito presente in ogni checkout del Lab
(è dipendenza pip di toolkit, SO, DI, data-explorer, ACB, lab-dashboard, eurostat, open-siope,
lab-ask). Il server discussions serve cross-repo e un repo separato sarebbe overkill per 7 tool MCP.

**Non è installabile via pip** — funziona solo da checkout. Configurazione in `opencode.json`:
