# Go continuation reproduction, 2026-11-16

The public Go cookbook's WatchInbox workflow was extracted into a disposable
managed runtime with deterministic fixture implementations of FetchInboxBatch
and HandleBatch. It started at cursor `cursor`, batch count 499. No external
inbox or payment provider was used.

Before this change, task `49ea6ebc4e344ac2a3165655e9ed5140` marked the old workflow
continued-as-new, but its continuation referenced its own task and no successor
executed. The focused Worker dispatch test failed in all four cases because no
enqueue occurred before completion.

With this implementation, managed runtime task
`32766764da49e9a0b4b245e58378fb27` completed with exit code 0 against staging
Agent orchestrator image revision `954b8260502a70aa6e50fc9a5f3f1a45b04d7578`.
The old run fetched `cursor`; a distinct successor fetched `cursor-next`, ran
HandleBatch, and recorded TimerStarted. The harness then terminated that
successor. The same runtime passed sequential map/reduce (3 records), approval
signal, activity heartbeat/milestone (10,000 fixture rows), transient retry on
attempt 3, and the expected non-retryable business failure. This does not prove
crash atomicity or arbitrary customer workflows.

Validation passed:

- `(cd go && GOWORK=off go test ./... && GOWORK=off go vet ./...)`
- `(cd go && GOWORK=off go test -race ./agent/worker)`
- `python3 go/protocol/tools/check_drift.py --self-test` and `--monorepo`
- `python3 scripts/check_package_layout.py --self-test` and without arguments
- `python3 scripts/generate_openapi.py --plane all --check`
- `python3 scripts/generate_api_docs.py --check`
- `python3 scripts/check_api_docs.py`

The HTTP fixture checks forwarding/defaults, enqueue-before-complete order,
enqueue failure, and identical idempotency key/body on completion redelivery.
Its server returns a fixed successor; it is not evidence of server-side
idempotency implementation. No wire contract or generated binding changed.
