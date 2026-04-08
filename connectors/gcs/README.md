# Connector `gcs`

Connector MCP read-only per ispezionare bucket Google Cloud Storage e verificare l'accessibilita' pubblica di URL GCS.

## Tool esposti

- `gcs_list_objects(bucket, prefix="")`
- `gcs_check_public(url)`

## Cosa fa

- elenca oggetti in un bucket GCS a cui le credenziali correnti hanno accesso
- verifica se un URL pubblico GCS risponde correttamente

## Cosa non fa

- upload
- delete
- signed URL
- integrazione BigQuery

## Config e credenziali

Le credenziali **non** stanno nel repo.

Questo connector usa le **Application Default Credentials** di Google Cloud.

Strade supportate:

1. login locale con:

```powershell
gcloud auth application-default login
```

2. oppure variabile ambiente standard:

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\percorso\service-account.json"
```

Il repo non deve contenere:

- file `.json` di service account
- token
- path macchina-specifici hardcoded

## Installazione dipendenze

In un ambiente Python dedicato:

```powershell
python -m pip install -r connectors/gcs/requirements.txt
```

## Esempio config MCP

Esempio locale da adattare al proprio ambiente:

```json
"gcs": {
  "command": "python",
  "args": ["connectors/gcs/server.py"]
}
```

Se vuoi usare un interprete specifico, cambia `command` in modo esplicito nel tuo file di config locale.

## Test minimi

Smoke test:

```powershell
python -c "import pathlib, runpy; runpy.run_path(str(pathlib.Path('connectors/gcs/server.py')))"
```

Elenco oggetti:

```powershell
python -c "from connectors.gcs.gcs_client import list_objects; print(list_objects('dataciviclab-clean', ''))"
```

Check URL pubblico:

```powershell
python -c "from connectors.gcs.gcs_client import check_public; print(check_public('https://storage.googleapis.com/dataciviclab-clean/example.parquet'))"
```

## Note operative

- `gcs_check_public` usa `HEAD` e, se il server non lo supporta bene, fa fallback a `GET` con `Range: bytes=0-0`
- il bucket `dataciviclab-clean` e' un caso d'uso del Lab, non una dipendenza hardcoded del connector
