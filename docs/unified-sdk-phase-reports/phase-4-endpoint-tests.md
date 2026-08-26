# Phase 4 checkpoint: exhaustive endpoint tests

Status: **BLOCKED — external live execution evidence required**

Updated: 2026-08-26

Design SHA-256: `4a35c1e1c89fea5a729d5d19fd00cc27824a8ae3e4cf1945d6741a382c9e0ad7`

Implementation-plan SHA-256: `15d1d37ef4372b57477f1cecee4eb796bdc8652d7680bf36501b9b47edee266e`

Contract-bundle SHA-256: `5b44c873737a135f75486b56f84cd534c0ac398dc87cdbc0150fd64c8cfcfcbd`

## Delivered

- Deterministic contract-derived fixtures and strict recorded transport for
  all 130 operations in Go, TypeScript, and Python (390 requests).
- Real cURL execution for all 121 eligible management/public operations and
  nine visible protocol exceptions with dedicated runners.
- Stable, server-bounded cursor pagination for Agent task events and workflow
  history. The three SDKs expose one-page and incremental APIs while preserving
  full-history convenience methods through automatic cursor following.
- `scripts/test_live_api.py`, a contract-aware live fixture manager that
  validates exact tier ownership and contract digest; generates a unique run
  prefix; restricts mutations to registered resources; captures explicit
  identifiers; refuses wildcard cleanup; requires three independent
  destructive-operation controls; redacts credentials; writes a mode-0600
  ledger; and cleans in reverse registration order.
- Safety self-tests proving reverse cleanup, destructive refusal, preservation
  of the primary failure, separate cleanup failures, and remaining-ID reports.
- Scheduled disposable-nightly, protected isolated pre-release, and
  production-smoke workflows. All three publishing workflows now depend on the
  reusable pre-release live job.
- Corrected cadence ownership: 104 ordinary operations are nightly, 24
  protocol/high-risk operations are pre-release, and two public read-only
  health operations are production smoke.

## Coverage evidence

| Plane | Operations | Go | TypeScript | Python | cURL | Protocol exceptions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Agent | 45 | 45 | 45 | 45 | 36 | 9 |
| Worker | 12 | 12 | 12 | 12 | 12 | 0 |
| Service | 73 | 73 | 73 | 73 | 73 | 0 |
| **Total** | **130** | **130** | **130** | **130** | **121** | **9** |

The pre-release tier owns delegated polling/refresh/signing, archive upload,
sandbox WebSocket, cancellable continuous Service logs, deployment
cancellation, and every Service operation marked destructive. The production
runner independently verifies its two-operation hard-coded allowlist is still
public and read-only before making a request.

## Design comparison and corrective actions

The earlier checkpoint had two valid design deviations:

1. Live cadence annotations were presented without an executable fixture
   manager, workflows, cleanup ledger, or release dependency. Those source
   gaps are corrected. Recorded evidence is still never labeled live.
2. Agent histories were complete unpaginated responses exempted from the
   transport bound. The coordinated server now returns stable cursor pages
   bounded by both item count and serialized bytes. Go walkers, TypeScript
   async generators, and Python iterators permit incremental consumption; each
   individual Agent response has a finite SDK bound.

The implementation comparison found and corrected an additional cadence
error: archive, WebSocket, continuous-log, cancellation, and destructive
Service operations had been assigned to ordinary nightly runs despite the
implementation plan reserving them for isolated pre-release coverage.

Review of the fixture safety boundary then found that a mutation could name a
registered `resourceKey` while its resolved request targeted a different
identifier. The manager now verifies the exact recorded identifier is present
in every targeted mutation, destructive, or protocol request before invoking
an adapter. Its self-test proves a mismatched ledger key and request identifier
fail closed. The correction is
`db1c7827643fb40c008573343635f093dbc7b69f`.

## Verification

| Check | Result |
| --- | --- |
| Contract generation, inventory, fixtures, and docs | PASS — 130 operations, bundle `5b44c873737a` |
| Recorded SDK conformance | PASS — 130 × 3 = 390 requests |
| Recorded cURL conformance | PASS — 121 real cURL processes |
| Live fixture-manager self-test | PASS |
| Production scenario static validation | PASS — two public/read-only operations |
| Go test/vet | PASS |
| TypeScript typecheck/build/test | PASS — 126 tests |
| Python wheel and native suite | PASS — 128 tests, one opt-in external skip |
| Agent Orchestrator test/vet and OpenAPI checker | PASS |
| Workflow syntax (`actionlint` 1.7.7) | PASS |
| Nightly disposable live execution | **BLOCKED** — protected environment/scenario not configured |
| Isolated pre-release live execution | **BLOCKED** — protected environment/scenario not configured |

## Remaining gate

The repository currently exposes only `github-pages`, `npm`, and `pypi`
GitHub Environments. It has no live environment variables, scenario secrets,
or successful nightly/pre-release run. Creating those protected environments
and supplying disposable deployment fixtures requires organization-owned
infrastructure and credentials that are not present in this workspace.

Phase 4 therefore remains blocked on execution evidence, not missing test
code. Once both live workflows pass against the coordinated server revision,
their ledgers and run URLs must be recorded here before changing this gate to
PASS.
