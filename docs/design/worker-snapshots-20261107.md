# Worker snapshot operations

## Problem and scope

Web adds five public Worker operations under a new **Snapshots** tag, so a
management token can do what the console's Worker Backup page does. Web's
[public Worker snapshots design](https://github.com/postgrip-io/postgrip-web/blob/main/docs/design/public-worker-snapshots-design-20261107.md)
owns the server behaviour and the contract. This slice mirrors that contract,
regenerates its derived outputs following the
[contract guide](../development/contracts.md), and adds idiomatic Worker
client methods in Go, TypeScript and Python. The Agent and Service contracts,
their clients and the runtime protocol do not change.

| operationId | Go | TypeScript | Python |
| --- | --- | --- | --- |
| `getWorkerSnapshotStatus` | `SnapshotStatus` | `snapshotStatus` | `snapshot_status` |
| `listWorkerSnapshots` | `Snapshots` | `snapshots` | `snapshots` |
| `createWorkerSnapshot` | `TakeSnapshot` | `takeSnapshot` | `take_snapshot` |
| `getWorkerSnapshotSettings` | `SnapshotSettings` | `snapshotSettings` | `snapshot_settings` |
| `updateWorkerSnapshotSettings` | `UpdateSnapshotSettings` | `updateSnapshotSettings` | `update_snapshot_settings` |

Python's `AsyncWorkerClient` has the same five methods.

## Design

### D1. Mirror and generation

`contracts/worker-openapi.json` is a byte-for-byte copy of web's
`postgrip-api/worker-openapi.json`. The generators produce the bindings, the
reference pages, the recorded fixtures, the operation inventory and the
coverage report. The bundle digest becomes
`87c0db92da44a39eb7a85c5f5b39186dbebc8e8f243cab5e1462838c7742a017`; the
package READMEs and the production-smoke scenario cite it. TypeScript publishes
the new generated names from `src/worker/index.ts`, recorded in
`test/public-surface.json`.

### D2. Idempotency and the write-only signing key

The two mutations take a required idempotency key, as `Check`, `Upgrade` and
the other Worker mutations do. A missing or invalid key is refused before
sending, through the idiomatic methods and the generated low-level clients.

`signingKey` appears only on `UpdateWorkerSnapshotSettingsRequest`, optional
and omitted when unset (Go `*string` with `omitempty`). No response type
declares it: settings answer `hasSigningKey`. Generated types are not edited;
tests in each language check that no snapshot answer type reaches a
`signingKey` field.

### D3. A snapshot run's lifetime

The server waits up to 5 minutes for a run before answering. Each Worker
client gives `createWorkerSnapshot` a 6-minute exchange lifetime, through the
per-call mechanism its executor already has: Go `transport.Call.Lifetime`,
TypeScript `ExecutorCall.lifetimeMs` and Python `Executor.exchange(timeout=...)`.
The lifetime only raises the configured timeout, never lowers a longer one,
and an earlier caller deadline, `AbortSignal` or cancellation still wins.
Python's timeout is urllib's socket timeout, so it bounds each blocking read,
not the whole exchange.

### D4. Retries

With retries enabled, the executors retry 408, 429, 502, 503 and 504 for
bounded reads and for mutations that carry an idempotency key, reusing the
key. Web's middleware does not keep `502` or `504` answers against the key,
and its contract says a resend after a `502` or `504` takes another snapshot.
A `504` `SNAPSHOT_UNCONFIRMED` run may still land. So `createWorkerSnapshot`
never retries a `502` or `504`: each executor call gains an optional set of
statuses it never retries (Go `Call.NoRetryStatuses`, TypeScript
`ExecutorCall.noRetryStatuses`, Python `no_retry_statuses`), and the Worker
plane sets it to `{502, 504}` for that operation. 408, 429, 503 and transport
failures keep the bounded retry with the same key. The other snapshot
operations are unchanged.

The Worker plane holds both settings in one per-operation policy table, applied
where the plane resolves every operation. The generated low-level client
follows the same policy as the idiomatic method.

The executors honour `Retry-After` only on 429 and 503, and never retry 409.
`409` `SNAPSHOT_IN_PROGRESS` is therefore returned at once, with its
`Retry-After` decoded on the Worker error (Go `RetryAfter`, TypeScript
`retryAfterMs`, Python `retry_after`) for the caller to wait on.

### D5. Test and live ownership

All five operations are recorded-tested and cURL-eligible. The two status and
settings reads are owned by the nightly tier: both answer whether or not
snapshots are on. `listWorkerSnapshots`, `createWorkerSnapshot` and
`updateWorkerSnapshotSettings` are owned by the pre-release tier: they need a
Worker with snapshots enabled on a storage destination whose credentials the
console delivered, and the settings write must restore the fixture Worker's
previous settings. The protected stage scenarios must add these steps (see the
[live-suites design](live-suites-on-stage-20261017.md), D3).

## Acceptance

- `generate_openapi.py --plane all --check`, the inventory, fixture, coverage,
  endpoint, cURL and API documentation checks pass.
- Go, TypeScript and Python suites pass, including tests for the routes, the
  idempotency keys, the write-only signing key, the run lifetime, no retry of
  `502` and `504` on a run, and `Retry-After` on `SNAPSHOT_IN_PROGRESS`.
- Web's discovery gate passes once web pins the merged commit.
