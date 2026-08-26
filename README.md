# lab-connectors — Libreria condivisa del DataCivicLab

Package Python condiviso per i repo del DataCivicLab: infrastruttura riusata
da più repo (HTTP client, MCP server core, client GCS, path contract GCS,
context manager DuckDB, utility per test).

## Package

| Package | Cosa fa |
|---|---|
| [`lab_connectors.http`](#http) | HTTP client con SSL fallback, retry, timeout, circuit breaker |
| [`lab_connectors.mcp`](#mcp) | Infrastruttura server MCP: factory, error handling, logging, cache |
| [`lab_connectors.gcs`](#gcs) | Client GCS (list, upload, verify) + path contract canonici |
| [`lab_connectors.duckdb`](#duckdb) | Context manager connessioni DuckDB + query helpers |
| [`lab_connectors.registry`](#registry) | Modelli e client per registry/registry.json |
| [`lab_connectors.testing`](#testing) | Fake HTTP client e utility per test |

Dettaglio API completo: [docs/api-reference.md](docs/api-reference.md)

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

# Sviluppo locale (tutto)
pip install -e ".[dev,mcp,gcs,duckdb]"
```

## HTTP client

Pattern canonico del Lab per chiamate HTTP: retry, SSL fallback, timeout.

```python
from lab_connectors.http import HttpClient

client = HttpClient(timeout=15)
result = client.get("https://www.dati.salute.gov.it/sitemap-0.xml")
assert result.is_ok
```

Include anche client SPARQL (`execute_sparql`, `discover_graphs`) e
`download()` per file binari con stesso fallback/retry.

## MCP server core

Factory standardizzata per i server MCP del Lab: init, error handling, logging, cache.

```python
from lab_connectors.mcp import create_mcp_server

mcp = create_mcp_server(
    name="toolkit",
    instructions="Read-only MCP per ispezione pipeline toolkit.",
)
```

`guard()` / `guard_timed()` per error handling standard, `McpError`/`ErrorCode`
(22 codici), `McpLogger` per logging strutturato, `TtlCache` per cache thread-safe.

## GCS

Client GCS unificato con 3 modalità (SDK, HTTP API, auto-fallback) e **path
contract canonici** — i path di tutti gli artifact del Lab su GCS, risolvibili
con `resolve()`, `gs_url()`, `https_url()`. Include upload/verifica
(`upload_file`, `upload_string`, `object_exists`) e il manifest GCS
(`read_manifest`), indice centralizzato dei file sui bucket pubblici.

```python
from lab_connectors.gcs.paths import resolve

path = resolve("clean_parquet", slug="ispra_ru_base", year=2024)
# → "ispra_ru_base/2024/ispra_ru_base_2024_clean.parquet"
```

## DuckDB

Context manager che elimina il pattern `connect() + try/finally + close()`.

```python
from lab_connectors.duckdb import safe_connect, gcs_connect

with safe_connect(":memory:") as con:
    result = con.execute("SELECT 1 AS x").fetchall()
```

`gcs_connect()` legge parquet direttamente da GCS: URL `https://...` in modo
nativo (senza estensioni, stabile); path `gs://...` o `s3://...` — inclusi
glob multi-year come `gs://bucket/slug/*/*.parquet` — caricando httpfs.

`load_mart_table()`, `load_clean()`, `query_clean()` caricano dati da GCS
come DataFrame — il punto di partenza per le dashboard Streamlit:

```python
from lab_connectors.duckdb.queries import load_mart_table, query_clean

df = load_mart_table("rna_aiuti_stato", "mart_aiuti_per_regione", 2023)

df = query_clean(
    "rna_aiuti_stato",
    "SELECT regione_beneficiario, SUM(elemento_aiuto) AS totale "
    "FROM clean_input GROUP BY regione_beneficiario ORDER BY totale DESC",
)
```

## Registry

Modelli e client per `registry/registry.json` — il catalogo degli artifact di ogni repo.

```python
from lab_connectors.registry import load_registry

reg = load_registry(Path("rna-aiuti-stato/registry/registry.json"))
# oppure da GitHub
reg = load_registry_github("rna-aiuti-stato")

for ds in reg.datasets:
    print(f"{ds.slug}: {ds.period} ({len(ds.columns)} cols)")

for sig in reg.signals:
    print(f"{sig.id}: {sig.status} — {sig.detail}")
```

`registry_to_dict()` converte le dataclass in dict per backward compat.

## Testing

`FakeHttpClient` sostituisce le chiamate HTTP reali con risposte pre-configurate,
senza monkeypatch. CLI `audit-test-markers` per verificare la copertura dei
marker pytest obbligatori.

## Cosa NON sta qui

- workflow canonici di pipeline (stanno in `toolkit`)
- skill e playbook (stanno in `lab-ops`)
- logica core di dataset (stanno nei repo dominio)
- tool MCP di dominio specifici (stanno nei rispettivi repo)

### Eccezione: `mcp_servers/github-discussions`

Il server MCP per GitHub Discussions (`mcp_servers/github-discussions/`) viola
la regola sopra perché è un server MCP di dominio, non un connector infrastrutturale.

**Perché sta qui**: `lab-connectors` è l'unico repo garantito presente in ogni
checkout del Lab (è dipendenza pip di toolkit, source-observatory,
dataset-incubator, data-explorer, agent-context-builder, lab-dashboard,
eurostat, italia-corpus, senato-akn, lab-ask, partecipate-monitor,
terzo-settore-intelligence, opere-pubbliche-intelligence). Il server
discussions serve cross-repo e un repo separato sarebbe overkill per 7 tool MCP.

**Non è installabile via pip** — funziona solo da checkout.

## Test

```bash
pytest tests/
ruff check lab_connectors/
mypy lab_connectors/
```
