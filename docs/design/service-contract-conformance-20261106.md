# Service contract conformance mirror

## Problem and scope

Web corrected its canonical Service contract to describe what the handlers
actually send. Web's
[Service OpenAPI conformance design](https://github.com/postgrip-io/postgrip-web/blob/main/docs/design/service-openapi-code-conformance-20261106.md)
owns the evidence and the decision. This slice mirrors that contract and
regenerates every output derived from it, following the
[contract guide](../development/contracts.md). Hand-written clients, runtime
adapters, transport and the Agent and Worker contracts do not change.

## Design

Copy `postgrip-api/service-openapi.json` byte-for-byte to
`contracts/service-openapi.json`, then regenerate through the generators only:
bindings, reference pages, recorded fixtures and coverage reports. The bundle
digest becomes `3ca06a52e739352e30f014e0e193836e785610f3d73e5f560c8205fe643ab5cb`;
the package READMEs and the production-smoke scenario cite it.

Generated surface changes, all describing current server behavior:

- TypeScript and Python `OpenAPIEnvironment.kind` is the environment kind
  (`preview`, `production`, `staging`, `development`, `custom`). Go models it
  as a plain string and is unchanged.
- `OpenAPIServiceRuntimeLogWorkerStatus.errorCode` and
  `OpenAPIServiceConfigurationTargetState.updatedAt` are removed in all three
  languages. The server never sends them, so a caller could only ever read them
  as absent. The SDK is pre-1.0, and the release notes must list the removal.
- `createServiceVolume`, `createServiceDomain` and `createServiceVariable`
  succeed with `202`, and several mutations document fence response headers.
  The generators treat every 2xx as success and do not model response headers,
  so the generated clients are unchanged by these.

## Acceptance

- `generate_openapi.py --plane all --check`, the operation inventory, recorded
  fixture, coverage, cURL and API documentation checks pass.
- Go, TypeScript and Python suites pass.
- Web's discovery gate passes once web pins the merged commit.

## Open gaps

Idiomatic Service clients do not expose the `Service-Catalog-ETag`,
`Service-Collection-ETag` and `Service-Project-ETag` headers, so an SDK caller
must read the collection again to get the next `If-Match`. Surfacing them is a
separate client change.
