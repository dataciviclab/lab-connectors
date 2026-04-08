# lab-connectors

Repository privato DataCivicLab per piccoli connettori e adapter che chiudono gap del workflow verso servizi esterni.

Questo repo nasce con un perimetro stretto.

Serve per:

- piccoli connettori DCL-specifici
- adapter verso servizi esterni usati nel workflow del Lab
- tooling utile su piu' repo ma che non appartiene a `lab-ops`
- codice troppo operativo per restare in `_local`, ma non abbastanza grande da giustificare un repo dedicato per ogni connettore

Non serve per:

- workflow canonici
- skill o playbook
- logica core di pipeline dataset
- tooling generico di stato locale
- MCP `toolkit`

Regola pratica:

- se il codice e' un workflow, una skill o un playbook, sta altrove
- se il codice e' introspezione o supporto diretto al motore `toolkit`, sta nel repo `toolkit`
- se il codice e' un adapter leggero verso servizi esterni usati dal Lab, questo repo e' il posto giusto

## Scope iniziale

I primi connettori presenti qui sono:

- `gcs`
- `github-discussions`

Eventuali wrapper futuri per MCP esterni come `ckan` o `sdmx` possono entrare qui solo se restano adapter leggeri del Lab e non duplicano il core upstream.

## Boundary del repo

Questo repo e' il posto giusto per connettori che sono:

- piccoli
- abbastanza stabili da essere condivisi col team
- chiaramente utili nel workflow del Lab
- piu' facili da mantenere insieme che come tanti repo minuscoli

Questo repo non e' il posto giusto per connettori che sono:

- troppo legati a stato personale o segreti locali
- ancora troppo sperimentali per essere condivisi
- piu' naturali come parte del repo `toolkit`

## Fase privata iniziale

Il repo parte privato.

Lo scopo di questa fase e':

- condividere i connettori col team
- testare struttura e setup
- ripulire config e documentazione
- decidere in seguito se aprire tutto o in parte

## Struttura iniziale

```text
connectors/
  gcs/
  github-discussions/
docs/
```

## Prossimi passi

1. consolidare boundary e convenzioni del repo mentre resta privato
2. testare uso reale dei connector col team
3. aggiungere eventuali adapter futuri solo se restano leggeri e coerenti col perimetro
4. decidere piu' avanti se il repo deve restare privato o aprirsi
