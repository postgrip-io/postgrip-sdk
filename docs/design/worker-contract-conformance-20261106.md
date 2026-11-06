# Worker contract conformance mirror

## Problem and scope

Web documented in its canonical Worker contract the refusals and input rules
the Worker handlers already enforce. Web's
[Worker OpenAPI conformance design](https://github.com/postgrip-io/postgrip-web/blob/main/docs/design/worker-openapi-code-conformance-20261106.md)
owns the evidence and the decision. This slice mirrors that contract and
regenerates its derived outputs, following the
[contract guide](../development/contracts.md). Hand-written clients, runtime
adapters, transport and the Agent and Service contracts do not change.

## Design

Copy `postgrip-api/worker-openapi.json` byte-for-byte to
`contracts/worker-openapi.json`, then regenerate through the generators only.
The bundle digest becomes
`8031543651e185f63f1155ec3cc236fa1f91f292aac0b1d2ee101ace74f52a39`; the
package READMEs and the production-smoke scenario cite it.

Every change is in descriptions, plus dropping `format: uuid` from
`recoveredFromWorkerId`, which all three generators already model as a string.
The generated Worker clients therefore change only in their contract digests,
and the reference pages gain the documented refusals:
`404` `CAPABILITY_NOT_ENABLED` on `createWorker`, `409`
`WORKER_UPGRADE_REQUIRED` on the log operations, `409` `LIFECYCLE_CONFLICT`
on maintenance and resume, and the `name`, `host`, `window` and `since` rules.

## Acceptance

- `generate_openapi.py --plane all --check`, the operation inventory, recorded
  fixture, coverage, endpoint, cURL and API documentation checks pass.
- Go, TypeScript and Python suites pass.
- Web's discovery gate passes once web pins the merged commit.
