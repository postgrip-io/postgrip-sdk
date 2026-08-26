# Live integration tiers

Pull requests prove all 130 operations through strict recorded transports in
Go, TypeScript, and Python and execute every eligible cURL example. Live jobs
add deployed-system evidence at a cadence matched to risk:

| Tier | Environment | Coverage |
| --- | --- | --- |
| Nightly | Protected disposable tenant | Ordinary tenant API lifecycles across Agent, Worker, and Service |
| Pre-release | Protected isolated runtime | Delegated signing/refresh, archive upload, cancellable logs, sandbox WebSocket, and destructive Service operations |
| Production smoke | Production-safe endpoints | Hard-coded public read-only `health` and `workerOrchestratorHealth` allowlist only |

The live fixture manager validates the selected operation set against
`test/operation-tests.json`, so a contract addition cannot silently escape a
live tier. Environment-specific scenarios are protected because they contain
deployment fixture details, but their schema and runner are versioned in this
repository.

Every run receives a unique `postgrip-sdk-…` prefix. Mutations may operate only
on registered resources, and cleanup uses captured identifiers in reverse
dependency order. Wildcards are rejected. Destructive calls require scenario,
environment, and command-line consent simultaneously. A mode-0600 JSON ledger
is uploaded even after failure and preserves the primary failure, cleanup
failures, and all remaining identifiers.

For the scenario format and local safety checks, see
[`test/live/README.md`](https://github.com/postgrip-io/postgrip-sdks/blob/main/test/live/README.md).
