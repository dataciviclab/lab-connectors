# Contributing to lab-connectors

Questa guida vale per la repo `lab-connectors`.

Per le regole GitHub condivise dell'organizzazione, parti prima da
[`.github`](https://github.com/dataciviclab/.github).

## A cosa serve questa repo

`lab-connectors` è il package Python condiviso per l'infrastruttura riusata
da più repo del DataCivicLab.

Qui stanno:

- `lab_connectors/http/` — HTTP client con SSL fallback, retry, timeout, SPARQL client e thread pool parallelo
- `lab_connectors/mcp/` — MCP server core: `create_mcp_server()`, `guard()`, `McpError`, `TtlCache`, `McpLogger`
- `lab_connectors/gcs/` — client GCS unificato (list, upload, object_exists, check_public)
- `lab_connectors/gcs/paths.py` — path contract canonico GCS (bucket, pattern, resolve, URL)
- `lab_connectors/duckdb/` — context manager `safe_connect()` e `gcs_connect()` per DuckDB
- `lab_connectors/testing/` — `FakeHttpClient` e `audit-test-markers` CLI per test

Qui non stanno:

- workflow canonici di pipeline — stanno in `toolkit`
- skill e playbook operativi — stanno in `lab-ops`
- tool MCP di dominio specifici — stanno nei rispettivi repo (`toolkit`, `source-observatory`)
- logica core di dataset o analisi — stanno in `dataset-incubator` o `dataciviclab`

## A chi serve

`lab-connectors` è una dipendenza pip degli altri repo del Lab:

| Repo | Dipende da |
|---|---|
Il core HTTP è sempre incluso nell'installazione base. Gli extra opzionali aggiungono funzionalità specifiche.

| Repo | Extra installati | Moduli usati |
|---|---|---|
| `toolkit` | `[mcp,duckdb]` | http, mcp, duckdb |
| `source-observatory` | `[gcs,mcp,duckdb]` | http, gcs, mcp, duckdb |
| `dataset-incubator` | `[gcs,mcp,duckdb]` | gcs, mcp, duckdb |
| `data-explorer` | `[duckdb,gcs]` | duckdb, gcs (path) |
| `agent-context-builder` | `[mcp]` | http, mcp |
| `lab-dashboard` | — (base) | gcs (path) |

Se modifichi `lab-connectors`, potresti impattare tutti questi repo.

## Setup locale

```bash
pip install -e ".[dev,mcp,gcs,duckdb]"
```

### Eseguire i test

```bash
pytest tests/
ruff check lab_connectors/
mypy lab_connectors/
```

I test sono organizzati per modulo:

| Directory / File | Cosa testa |
|---|---|
| `tests/http/` | HTTP client (client, backoff, pool, SPARQL, FakeHttpClient) |
| `tests/mcp/` | MCP core: guard, errori, cache, logging |
| `tests/test_duckdb.py` | DuckDB safe_connect, gcs_connect |
| `tests/test_gcs_paths.py` | Path contract GCS (`paths.json`, resolve, gs_url, parse_gs_url) |
| `tests/test_gcs.py` | GCS client (list, upload, object_exists, check_public) |
| `tests/test_audit_markers.py` | Audit marker CLI (`audit-test-markers`) |

## Installazione parziale

`lab-connectors` supporta installazioni con extra selettivi:

```bash
# Solo HTTP client (nessuna dipendenza extra)
pip install lab-connectors

# Con MCP core
pip install lab-connectors[mcp]

# Con DuckDB
pip install lab-connectors[duckdb]

# Con GCS
pip install lab-connectors[gcs]

# Con testing utilities (FakeHttpClient, audit CLI)
pip install lab-connectors[dev]

# Sviluppo locale (tutto)
pip install -e ".[dev,mcp,gcs,duckdb]"
```

## Quando aprire una issue

Apri una issue in `lab-connectors` se il lavoro riguarda:

- bug o miglioramenti a uno dei moduli condivisi
- aggiunta di un nuovo connector o adapter
- cambio di contratto che impatta i consumer downstream
- aggiornamento dipendenze o compatibilità Python

Per discutere l'architettura prima di aprire una issue, usa una
Discussion in `dataciviclab`.

## Prima di aprire una PR

- verifica se esiste già una issue collegata
- tieni il perimetro stretto: una PR = un modulo o un fix
- se cambi un'interfaccia pubblica (firma di funzione, classe, eccezione),
  aggiorna anche i consumer nei repo che dipendono da `lab-connectors`
- controlla che `ruff check .` e `mypy .` passino
- aggiungi o aggiorna i test per il modulo modificato
- se aggiungi un nuovo extra, aggiorna `pyproject.toml` e questo file

## Riferimenti

- [README.md](README.md) — documentazione completa dei moduli
- [pyproject.toml](pyproject.toml) — dipendenze e configurazione package
- [`toolkit`](https://github.com/dataciviclab/toolkit) — consumer HTTP, MCP, DuckDB
- [`source-observatory`](https://github.com/dataciviclab/source-observatory) — consumer HTTP, GCS, MCP, DuckDB
- [`dataset-incubator`](https://github.com/dataciviclab/dataset-incubator) — consumer GCS, MCP, DuckDB
- [`data-explorer`](https://github.com/dataciviclab/data-explorer) — consumer DuckDB, GCS path
- [`agent-context-builder`](https://github.com/dataciviclab/agent-context-builder) — consumer HTTP, MCP
- [`.github`](https://github.com/dataciviclab/.github) — policy condivise
