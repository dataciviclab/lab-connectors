# lab-connectors

Package Python condiviso per i repo del DataCivicLab.

---

## Package disponibili

### `lab_connectors.http`

HTTP client con SSL fallback, retry e timeout. Pattern canonico del Lab.

```python
from lab_connectors.http import HttpClient, HttpResult

# GET con SSL fallback
client = HttpClient(timeout=15)
result = client.get("https://www.dati.salute.gov.it/sitemap-0.xml")
assert result.is_ok  # True se la response è usable

# HEAD con SSL fallback
result = client.head("https://example.com/")
assert result.response.status_code == 200

# Diagnostica SSL fallback
assert result.ssl_fallback_used is None  # primary SSL ok
# result.ssl_fallback_used == True        # primary SSL failed, fallback succeeded
# result.ssl_fallback_used == False       # entrambi falliti
```

---

## Scopo di questo repo

Package Python condivisi tra i repo del Lab.

**Non serve per**:
- workflow canonici (stanno nei repo che li eseguono)
- skill o playbook (stanno in `lab-ops`)
- logica core di pipeline dataset (stampa in `toolkit`)
- adapter MCP (stanno in `lab-ops/mcp/`)

---

## Installazione

```bash
# Editable install (sviluppo locale)
pip install -e .

# Con dipendenze dev
pip install -e ".[dev]"
```

---

## Test

```bash
pytest tests/
ruff check lab_connectors/
mypy lab_connectors/
```
