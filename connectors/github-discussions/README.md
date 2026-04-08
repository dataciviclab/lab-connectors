# Connector `github-discussions`

Connector MCP minimale per leggere e interagire con le GitHub Discussions via GraphQL API.

## Tool esposti

- `github_list_discussions`
- `github_get_discussion`
- `github_get_discussion_summary`
- `github_get_discussion_comments`
- `github_create_discussion`
- `github_add_discussion_comment`

## Cosa fa

- legge Discussions di un repository
- legge commenti top-level e reply annidate
- crea nuove discussion
- aggiunge commenti top-level

## Cosa non fa

- reactions
- edit
- moderation
- sync con draft locali
- gestione completa di thread avanzati fuori dal perimetro v1

## Config e credenziali

Le credenziali **non** stanno nel repo.

Questo connector richiede:

```powershell
$env:GITHUB_TOKEN = "<token>"
```

Il token deve avere scope sufficienti per leggere o scrivere Discussions nel repository target.

Il repo non deve contenere:

- token hardcoded
- file con segreti
- config locali macchina-specifiche

## Installazione dipendenze

In un ambiente Python dedicato:

```powershell
python -m pip install -r connectors/github-discussions/requirements.txt
```

## Esempio config MCP

Esempio locale da adattare:

```json
"github-discussions": {
  "command": "python",
  "args": ["connectors/github-discussions/server.py"],
  "env": {
    "GITHUB_TOKEN": "${GITHUB_TOKEN}"
  }
}
```

## Run manuale

```powershell
$env:GITHUB_TOKEN = "<token>"
python connectors/github-discussions/server.py
```

## Note operative

- focus volutamente stretto sulle Discussions
- reply annidate incluse nella lettura commenti
- `github_add_discussion_comment` aggiunge solo commenti top-level
