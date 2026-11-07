# Worker storage destinations

## Problem and scope

`updateWorkerSnapshotSettings` names a storage destination by its id, but a
management token had no way to find that id. Web adds one read-only public
Worker operation under the **Snapshots** tag. Web's
[public storage destinations design](https://github.com/postgrip-io/postgrip-web/blob/main/docs/design/public-storage-destinations-design-20261107.md)
owns the server behaviour and the contract. This slice mirrors that contract,
regenerates its derived outputs following the
[contract guide](../development/contracts.md), and adds an idiomatic Worker
client method in Go, TypeScript and Python. The Agent and Service contracts,
their clients and the runtime protocol do not change.

| operationId | Go | TypeScript | Python |
| --- | --- | --- | --- |
| `listStorageDestinations` | `StorageDestinations` | `storageDestinations` | `storage_destinations` |

Python's `AsyncWorkerClient` has the same method. The names are the ones web's
Worker API reference already shows. They follow the plane's convention of
naming a list read after what it lists (`Snapshots`, `Assignments`).

## Design

### D1. Mirror and generation

`contracts/worker-openapi.json` is a byte-for-byte copy of web's
`postgrip-api/worker-openapi.json`. The generators produce the bindings, the
reference pages, the recorded fixture, the operation inventory and the
coverage report. The bundle digest becomes
`20dec2d85e3bdbf1943c2e95d09ad184847196c83341e7cc940d33ed156a37fe`; the
package READMEs and the production-smoke scenario cite it. TypeScript publishes
the new generated names from `src/worker/index.ts`, recorded in
`test/public-surface.json`. Go also gets the generated `StorageDestination`
and `StorageDestinationList` aliases.

### D2. The read

`GET /api/v1/storage-destinations` takes no path, query or body and no
idempotency key. It answers every destination of the token's organization,
ordered by name, not paged, so the method returns the whole
`StorageDestinationList` and there is no pager. The operation is a bounded
read: with retries enabled it keeps the executors' bounded retry, and no
per-operation call policy applies. `region`, `endpoint`, `accountId` and
`prefix` are optional and absent when unset (Go `*string` with `omitempty`).

The answer carries no credential: the access key and secret stay on the
Workers. Generated types are not edited; tests in each language check that the
destination type declares exactly the contract's fields.

### D3. Test and live ownership

The operation is recorded-tested and cURL-eligible. It is owned by the nightly
tier: it is a read that needs only the stage organization's token, and an
organization with no destination answers `{"items": []}`. The protected stage
nightly scenario must add the step (see the
[live-suites design](live-suites-on-stage-20261017.md), D3).

## Acceptance

- `generate_openapi.py --plane all --check`, the inventory, fixture, coverage,
  endpoint, cURL and API documentation checks pass.
- Go, TypeScript and Python suites pass, including tests for the route, the
  absence of a query and an idempotency key, the empty list, the bounded read
  retry and the declared fields.
- Web's discovery gate passes once web pins the merged commit.
