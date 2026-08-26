# Phase 1 generation gate

Status: **PASS**

Completed: 2026-08-25 (America/Los_Angeles)

Reviewer: Codex implementation conformance review

## Revision and contract baseline

- Design SHA-256: `1868629d5c969122490045784f0a3cf87747028b6dd9ecd9df3aff541b3d1fab`
- Implementation-plan SHA-256: `e548a76a725210f116fe0663df40b421c4260d4a9a8c7cd35c6c5730d429e32e`
- Coordinated server contract commit:
  `be2b080161b58d9a294b6c5b144a8a188c162779`
- Contract-bundle digest:
  `b728fee5bceb4d246fe7ce81c1583d228d4f16d8f530179950fd5dccb2954820`

## Scope delivered

- Moved the only writable contract mirrors to `contracts/` and synchronized
  them byte-for-byte with the Phase 0 server commit.
- Extended the generator with plane and language selection plus an optional
  repository-relative output root.
- Added required metadata validation for operation class, credentials, safety,
  protocol, idempotency, pagination, and retry behavior.
- Embedded one contract-bundle digest in every generated Go, TypeScript, and
  Python plane surface.
- Generated an immutable, digest-bound operation inventory for all 130 public
  operations.
- Added closed JSON Schemas and complete checked-in ownership/behavior
  sidecars.
- Added a fail-loud checker for duplicates, stale or missing operation IDs,
  unknown fields, missing ownership, and unexplained cURL exceptions.
- Updated runtime-contract drift tooling to consume the new Agent contract
  location.
- Removed the stale public `compact` API after global administration moved to
  the server-only contract.

## Requirement traceability

| Requirement | Implementation | Test evidence |
| --- | --- | --- |
| Deterministic generation | `scripts/generate_openapi.py` sorted traversal and repository-relative output mode | two independent temporary output trees compared byte-for-byte |
| Plane/language selection | `--plane`, `--language`, and `--output-dir` | isolated Go, TypeScript, Python, and inventory generation smoke checks |
| Every operation represented | `test/operation-inventory.json` | 45 Agent + 12 Worker + 73 Service operations; no duplicate IDs |
| Required metadata generated | inventory metadata fields and generator validation | generation fails on missing metadata; inventory checker passes |
| Closed annotations | three schemas under `test/`; tests and notes sidecars | checker self-test rejects a stale ID and missing protocol exception |
| Shared digest | exported generated constants in all nine plane/language surfaces | generation drift checks and native compilers pass |
| No duplicate generated trees | one writable binding surface per current plane/language package | source-tree inventory review; Python `generated/openapi.py` files are import-only compatibility shims |
| Contract and runtime drift | contract source checks plus updated protocol drift path | all three generator `--check` runs and monorepo drift check pass |

## Commands and summarized results

- `python3 scripts/generate_openapi.py --plane <agent|worker|service>`: generated
  130 total operations.
- All three generator `--check` commands: passed.
- Two clean temporary generation trees plus per-language output selection:
  byte-identical and passed.
- `python3 scripts/check_operation_inventory.py --self-test`: passed.
- `python3 scripts/check_operation_inventory.py`: passed with 130 ownership
  and 130 behavior records.
- `python3 protocol/tools/check_drift.py --self-test` and `--monorepo`: passed
  for 59 protocol-backed OpenAPI models and eight runtime-only models.
- Go test and vet across the protocol and all current Go packages: passed.
- TypeScript install, typecheck, build, and tests across all three current
  packages: passed (94 tests).
- Python wheel builds and native tests across all three current packages:
  passed (114 tests, one environment-dependent skip).
- Contract mirror SHA-256 values match the Phase 0 report exactly.

## Inventory and annotation report

| Plane | Operations | cURL eligible | Protocol runner |
| --- | ---: | ---: | ---: |
| Agent | 45 | 36 | 9 |
| Worker | 12 | 12 | 0 |
| Service | 73 | 73 | 0 |
| Total | 130 | 121 | 9 |

The protocol-owned Agent exceptions cover signed mutations, long polling,
session refresh, archive upload, and WebSocket connection. Each record names a
reason, owner, and runner; none is counted as cURL coverage.

## Deviations and corrective actions

The synchronized public Agent contract no longer contains the server-global
`compact` operation, but compatibility tests and handwritten TypeScript/Python
facades still referenced it. This was an implementation defect relative to the
Phase 0 global-admin separation. The method, aliases, and expectations were
removed in all languages and all cumulative suites were rerun successfully.

The first drift-check run still classified `CompactRequest` and
`CompactResponse` as public OpenAPI-owned protocol models. Their ownership
entries were removed from the public generator while the server may continue
to use its internal admin contract. The drift check then passed.

No unresolved Phase 1 deviations remain.

## Remaining risks

- Package consolidation has not happened yet; the generated files still live
  in the three current artifact roots. Phase 2 moves them once and removes the
  old roots, so this is sequenced work rather than a duplicate source tree.
- Registry ownership and coordinated server deployment remain the release
  risks recorded in Phase 0.
