# Agent contract conformance mirror

## Problem and scope

Web corrected descriptions in its canonical Agent contract that claimed
behavior the Agent orchestrator does not have, and documented rules it
enforces. Web's
[Agent OpenAPI conformance design](https://github.com/postgrip-io/postgrip-web/blob/main/docs/design/agent-openapi-code-conformance-20261106.md)
owns the evidence and the decision. This slice mirrors that contract and
regenerates its derived outputs, following the
[contract guide](../development/contracts.md). Hand-written clients, the Go
protocol types, runtime adapters and transport do not change.

## Design

Copy `postgrip-api/agent-openapi.json` byte-for-byte to
`contracts/agent-openapi.json`, then regenerate through the generators only.
The bundle digest becomes
`25b5b43e3695f74e5388f060ade3e005d5791cfa42fba3f4a7a9cba1db2a72f6`; the
package READMEs and the production-smoke scenario cite it.

Every change is in descriptions, so the generated Agent clients change only in
their contract digests. The reference pages now say that backfill truncates to
100 runs, that `credentialRefs` is refused, which `createSandbox` limits apply,
that schedule `reason` values are discarded, which sandbox connect refusals are
plain text, and that `health` is not the only public route.

## Acceptance

- `generate_openapi.py --plane all --check`, the operation inventory, recorded
  fixture, coverage, endpoint, cURL, API documentation and runtime drift checks
  pass.
- Go, TypeScript and Python suites pass.
- Web's discovery gate passes once web pins the merged commit.
