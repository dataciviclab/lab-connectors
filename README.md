# lab-connectors

Private DataCivicLab repository for small connectors and adapters that close workflow gaps across external services.

This repo is intentionally narrow.

It is for:

- small DCL-specific connectors
- adapters around external services used in the Lab workflow
- tools that are useful across repos but do not belong in `lab-ops`
- code that is too operational to leave in `_local`, but not big enough to justify a dedicated repo per connector

It is not for:

- canonical workflows
- skills or playbooks
- dataset pipeline logic
- generic local state tooling
- the `toolkit` MCP

## Initial scope

The first connectors expected here are:

- `gcs`
- `github-discussions`

Future wrappers for external MCPs such as `ckan` or `sdmx` may live here only if they remain thin DCL adapters and do not duplicate the upstream core.

## Repo boundary

Use this repo for connectors that are:

- small
- stable enough to be shared with the team
- clearly useful in the Lab workflow
- easier to maintain together than as separate tiny repos

Keep out connectors that are:

- strongly tied to personal state or local secrets
- still experimental and not worth sharing yet
- better treated as part of `toolkit`

## Private-first phase

This repo starts private.

The purpose of the private phase is to:

- share the connectors with the team
- test structure and setup
- clean up config and docs
- decide what, if anything, should later become public

## Proposed structure

```text
connectors/
  gcs/
  github-discussions/
docs/
```

## Next steps

1. add the first two connectors in private form
2. remove local path assumptions and secret leakage
3. document setup and env handling
4. decide later if the repo should stay private or be opened
