## Sintesi

Descrivi in poche righe cosa cambia e perché.

## Contesto collegato

Closes #

## Cosa cambia

- [ ] Nuovo connector o modulo
- [ ] Modifica interfaccia pubblica (firma funzione, classe, eccezione)
- [ ] Bug fix
- [ ] Refactor / performance
- [ ] Dipendenze o extra (pyproject.toml)
- [ ] Documentazione
- [ ] CI

## Impatto su consumer downstream

lab-connectors è usato da: toolkit, source-observatory, dataset-incubator, data-explorer, agent-context-builder, lab-dashboard.

- [ ] Nessun impatto su interfacce pubbliche
- [ ] Modifica interfaccia pubblica → **consumer aggiornati** nei repo che dipendono dal modulo
- [ ] Nuovo extra → aggiornato `pyproject.toml` e README

## Verifica

```bash
pytest tests/
ruff check lab_connectors/
mypy lab_connectors/
```

- [ ] `pytest tests/` passa
- [ ] `ruff check lab_connectors/` passa
- [ ] `mypy lab_connectors/` passa
- [ ] Test nuovi o aggiornati per il modulo modificato

## Checklist PR

- [ ] Perimetro stretto: una PR = un modulo o un fix mirato
- [ ] Issue collegata o motivazione dell'assenza
- [ ] Se nuovo extra: `pyproject.toml` + README + CONTRIBUTING aggiornati

## Note per chi revisiona

Rischi, limiti, punti da controllare con attenzione.
