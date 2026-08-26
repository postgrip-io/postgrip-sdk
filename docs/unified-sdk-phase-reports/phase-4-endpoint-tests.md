# Phase 4 checkpoint: exhaustive endpoint tests

Status: **PASS**

Completed: 2026-08-26

Design SHA-256: `c381af949ea5da1378462c1a130d8fb43742e6cd3ab7fd246111210e8471aa6a`

Implementation-plan SHA-256: `e548a76a725210f116fe0663df40b421c4260d4a9a8c7cd35c6c5730d429e32e`

Contract-bundle SHA-256: `b728fee5bceb4d246fe7ce81c1583d228d4f16d8f530179950fd5dccb2954820`

## Delivered

- Added deterministic, contract-derived, schema-valid recordings for all 130
  public operations and a non-mutating fixture drift check.
- Added generated low-level operation dispatch to Go, TypeScript, and Python.
  This exposes every ordinary generated operation without bypassing the
  language SDK transport, while archive upload and WebSocket upgrade remain
  on their required custom adapters.
- Added one recording server and native Go, TypeScript, and Python runners.
  The server validates method, route expansion, repeated queries, required
  headers, JSON or archive bytes, content type, authentication class,
  Agent `agent-task-v1` signing bytes and key ID, and response decoding.
- Added dedicated native WebSocket protocol runs in all three languages.
  Archive upload goes through each SDK's streaming adapter, and signed Agent
  operations are cryptographically verified by the recording server.
- Added `scripts/check_operation_coverage.py` and checked-in JSON and Markdown
  coverage reports. The report derives expected counts from the contract and
  verifies immutable docs, generated ownership in every language, fixtures,
  recorded runner ownership, cURL, and visible protocol exceptions.
- Preserved selectable `--plane` execution for focused diagnosis. The all,
  Agent, Worker, and Service modes pass independently.

## Coverage evidence

| Plane | Operations | Go | TypeScript | Python | cURL | Protocol exceptions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Agent | 45 | 45 | 45 | 45 | 36 | 9 |
| Worker | 12 | 12 | 12 | 12 | 12 | 0 |
| Service | 73 | 73 | 73 | 73 | 73 | 0 |
| **Total** | **130** | **130** | **130** | **130** | **121** | **9** |

The recorded endpoint suite performs 390 language-operation ownership checks.
Live cadence ownership is complete: 121 nightly disposable, seven isolated
pre-release, and two production-safe smoke operations. External live jobs are
credential- and environment-gated; the pull-request gate uses the complete
recorded suite, while Phase 0's disposable PostgreSQL and isolated server
integration tests supply the coordinated server-side authentication evidence.

## Requirement traceability

| Requirement | Implementation | Evidence |
| --- | --- | --- |
| Every public operation is owned | Contract-derived fixtures and `operation-tests.json` | Coverage report: 130/130 |
| Every language sends the correct wire request | Native SDK runners against one strict recorder | 390/390 checks |
| One management token crosses management planes | Shared root clients and management auth lanes | Agent, Worker, and Service recordings use one `POSTGRIP_TOKEN` |
| Runtime credentials do not leak to management | Recorder asserts credential class per operation | All Agent management and delegated recordings pass |
| Management credentials do not leak to public bootstrap | Auth-lane-aware Agent transports plus regressions | Go, TypeScript, and Python public-operation tests pass |
| Signed runtime mutations retain protocol bytes | Ed25519 verification of `agent-task-v1` canonical payloads | Five signed operation recordings pass in every language |
| Protocol exceptions remain explicit | Nine owner/reason/runner annotations | Coverage report: 9 exceptions, none counted as cURL |
| Secure cURL remains executable | Real cURL recorder from Phase 3 rerun | 121/121 examples pass |

## Design comparison and corrective actions

The end-of-phase design comparison found and corrected four deviations before
this checkpoint passed:

1. Generated clients exposed typed methods but had no uniform way for the
   contract-derived runner to dispatch every operation. Each language now has
   a generated low-level operation-ID entry point that still uses the real SDK
   transport and rejects protocols needing a custom adapter.
2. The Agent transport inherited the management bearer on public session
   refresh. All three implementations now model management authorization
   separately, and focused regressions prove public requests omit it.
3. The first fixture sampler did not honor `minItems`, `minLength`, or two
   contract patterns. The shared documentation/fixture sampler now produces
   schema-valid values, and affected immutable examples were regenerated.
4. Focused `--plane` runs originally launched runners over all fixture
   directories. Each native runner now honors the selected plane, and all four
   selection modes pass.

After these corrections, no unexplained Phase 4 design deviation remains.

## Verification

| Check | Result |
| --- | --- |
| `python3 scripts/generate_test_fixtures.py --check` | PASS — 130 schema-valid recordings |
| `python3 scripts/check_operation_coverage.py` | PASS — 130 documented/generated/recorded |
| `python3 scripts/test_api_endpoints.py --plane all --mode recorded` | PASS — 390 checks |
| Focused Agent, Worker, and Service endpoint modes | PASS — 135, 36, and 219 checks |
| `python3 scripts/test_curl_examples.py --plane all --mode recorded` | PASS — 121 cURL operations |
| Go native suite and vet | PASS |
| TypeScript typecheck, build, and native suite | PASS — 112 tests |
| Python native suite | PASS — 121 tests, one opt-in live skip |
| Documentation generation and static checks | PASS — 130 pages |
| `git diff --check` | PASS |

## Remaining risks

Nightly and pre-release calls intentionally require configured disposable or
isolated infrastructure and are never silently redirected to production.
Their workflow safety gates and release cadence are finalized in Phase 5.
