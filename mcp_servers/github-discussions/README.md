# Connector `github-discussions`

Connector MCP per interagire con le GitHub Discussions via GraphQL API.

## Tool esposti

- `github_list_discussions` — elenca discussions con cursor pagination
- `github_search_discussions` — full-text search su titolo, body, commenti (NEW)
- `github_get_discussion` — dettaglio singola discussion (mode=full|summary)
- `github_get_discussion_summary` — riepilogo rapido
- `github_get_discussion_comments` — commenti e reply annidate
- `github_create_discussion` — nuova discussion
- `github_add_discussion_comment` — commento top-level

## Cosa fa

- legge e cerca Discussions di un repository
- legge commenti top-level e reply annidate
- **cerca per testo** su titolo, body e commenti
- **cursor pagination** per scorrere liste lunghe
- crea nuove discussion
- aggiunge commenti top-level

## Cosa non fa

- edit/delete di discussion o commenti
- reactions
- moderation
- sync con draft locali

## Token

Il server cerca il token GitHub in quest'ordine:

1. `GITHUB_PERSONAL_ACCESS_TOKEN`
2. `GITHUB_TOKEN`
3. `GH_TOKEN`

Il token deve avere scope sufficienti per leggere o scrivere Discussions nel repository target.

## Installazione

> **Nota:** Il server non è installabile via pip (non è un pacchetto Python).
> Funziona solo da checkout del repository. Assicurati di avere il repo clonato.

Dipendenze Python (richieste per il server e la libreria `lab_connectors`):

```sh
pip install -r mcp_servers/github-discussions/requirements.txt
pip install -e ".[mcp]"    # installa lab_connectors con extras mcp
```

## Config MCP (opencode.json / .mcp.json)

```json
"github-discussions": {
  "command": ["python", "/path/to/lab-connectors/mcp_servers/github-discussions/server.py"],
  "enabled": true
}
```

Il token va passato via environment (già configurato in `.env` o nella shell).

## Note operative

- focus stretto sulle Discussions
- reply annidate incluse nella lettura commenti
- `search_discussions` usa la GitHub Search API, limitata al repository
- `list_discussions` supporta `after`/`before` cursor dalla risposta `page_info`
- `list_discussions` con `category_name`: il filtro è applicato lato client **dopo** la paginazione GitHub. Con paginazione attiva, `discussion_count` può essere 0 anche se discussioni della categoria esistono più avanti. `total_count` è il conteggio globale non filtrato.
- `after` e `before` sono passati come variabili GraphQL (nessuna interpolazione in stringa)
