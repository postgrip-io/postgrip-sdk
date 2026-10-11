> Historical record. Original status, findings and validation below describe
> the recorded revision, not current policy or current release clearance. See
> [current owners](../../index.md) and [release gates](../../releasing.md).

# Phase 3 checkpoint: detailed documentation and cURL

Status: **PASS**

Completed: 2026-08-26

Design SHA-256: `4a35c1e1c89fea5a729d5d19fd00cc27824a8ae3e4cf1945d6741a382c9e0ad7`

Implementation-plan SHA-256: `15d1d37ef4372b57477f1cecee4eb796bdc8652d7680bf36501b9b47edee266e`

Contract-bundle SHA-256: `5b44c873737a135f75486b56f84cd534c0ac398dc87cdbc0150fd64c8cfcfcbd`

## Delivered

- Added deterministic `scripts/generate_api_docs.py` generation with a
  non-mutating `--check` mode.
- Published one immutable page for each of the 130 public operations, grouped
  by plane and resource tag. Each page records the exact plane and bundle
  digests, route, parameters, schemas, illustrative request and response,
  stable error envelope, credential class, scope alternatives, safety,
  idempotency, retry, pagination, lifecycle notes, related operations, and
  wire examples.
- Generated secure cURL for all 121 eligible HTTP management operations.
  Bearers enter cURL through standard-input configuration, never argv;
  request bodies use mode-0600 temporary files with trap cleanup.
- Kept the nine signed, streaming, long-polling, archive, or WebSocket Agent
  operations visible as owned protocol exceptions. Their pages omit invalid
  unsigned or unframed raw examples and name the dedicated runner and owner.
- Added Go, TypeScript, and Python raw HTTP examples for every normal HTTP
  operation, plus language-specific installation, authentication,
  configuration, migration, and root-client documentation.
- Added the immutable `/reference/<bundle>/` publication tree and a generated
  `/reference/latest/` redirect. Each language package embeds the bundle
  digest and links to the matching immutable reference.
- Added a unified MkDocs site and retained the three language documentation
  sites under their stable paths.

## Coverage evidence

| Plane | Operations | Secure cURL | Protocol exceptions |
| --- | ---: | ---: | ---: |
| Agent | 45 | 36 | 9 |
| Worker | 12 | 12 | 0 |
| Service | 73 | 73 | 0 |
| **Total** | **130** | **121** | **9** |

`scripts/check_api_docs.py` verifies exact operation-page ownership, required
sections and contract facts, immutable package links, protected-body handling,
bearer placement, literal-token absence, and complete protocol-exception
metadata. `scripts/test_curl_examples.py` executes a real cURL process for all
121 eligible operations against a recording HTTP server. The server checks
method, path, required query, required headers, JSON body, and authentication;
the runner also captures cURL argv and fails if the expanded token or
authorization header appears there.

## Design comparison and corrective actions

The end-of-phase comparison found and corrected four deviations before this
checkpoint passed:

1. Path-level OpenAPI parameters were being overwritten when an operation
   also declared its own parameters. The generator now merges both lists, and
   the real cURL suite proved the missing Worker and Service path values.
2. Initial mutation examples placed illustrative JSON inline. All request
   bodies now use protected temporary files, which also gives secret-bearing
   operations the safe default required by the design.
3. Several retained Agent guides still named former repositories, standalone
   artifacts, versions, or example paths. They now describe the three unified
   language packages, singular plane subpaths, version 0.13.0, and the current
   monorepo layout.
4. Generated raw Python examples followed redirects with the management
   bearer, and the equivalent Go snippets inherited a broader-than-exact
   sensitive-header redirect policy. All generated Go, TypeScript, and Python
   examples now refuse redirects. The documentation validator rejects a page
   that omits any language guard. This correction is recorded in
   `9e35ddf2a4fbe68ec8cb3f73f6f01bb96576da14`.

After those corrections, no unexplained Phase 3 design deviation remains.

## Verification

| Check | Result |
| --- | --- |
| `python3 scripts/generate_api_docs.py --check` | PASS — 130 operations |
| `python3 scripts/check_api_docs.py` | PASS — 130 pages, 121 cURL examples |
| `python3 scripts/test_curl_examples.py --plane all` | PASS — Agent 36, Worker 12, Service 73 |
| Root `mkdocs build --strict` | PASS |
| TypeScript `mkdocs build --strict` | PASS |
| Python `mkdocs build --strict` | PASS |
| `go test ./...` | PASS |
| Python native unit suite | PASS — 119 tests, one opt-in live skip |
| Protocol drift self-test and monorepo check | PASS — 67 types |
| `git diff --check` | PASS |

The exhaustive three-language client recordings and dedicated protocol
runners remain Phase 4 work; cURL generation and execution required by this
phase are complete.
