# Go workflow continuation

## Behavior and ownership

The Go cookbook's inbox workflow must enqueue a successor with a fresh history
before completing its current task as continued-as-new. The existing Go worker
only completes the current task and incorrectly points the continuation at that
same task. The Agent orchestrator records completion; it does not enqueue the
successor from that result.

The Go worker owns this two-request orchestration. It uses the existing typed
Connection operations and WorkflowPayload; transport, contracts, authentication
and public method signatures remain unchanged. The context supplies current
workflow type and queue defaults. The worker chooses a stable successor workflow
ID from the current task ID when no explicit ID is provided. It forwards args,
namespace, lease timeout, run timeout and retry policy, and records the previous
workflow ID in continuedFromWorkflowId. Completion references the returned new
task ID, never the current task.

Enqueue uses a stable idempotency key derived from the current task ID. If either
request fails, leave the current task leased for expiry/redelivery, without
failing or completing it prematurely. Redelivery resends the same enqueue body
and key, allowing the server's 24-hour idempotency window to return the original
successor. This is not an atomic transaction: the successor can run before the
old completion is persisted. There is no indefinite deduplication guarantee
beyond that window. Correct the existing atomicity claim in current Go docs.

## Validation

Exercise the real Worker dispatch and HTTP adapter with a local server: default
and explicit options, argument propagation, enqueue-before-complete ordering,
returned successor ID, enqueue failure, and completion failure followed by
redelivery with the same idempotency key/body. Run all Go tests/vet and SDK
contract/layout checks. Then execute the literal cookbook workflow on a disposable
managed Agent runtime, observing a distinct successor execute its supplied state.
Record live evidence separately from this design and do not equate a recorded
transport test with deployment validation.
