# Contract-driven SDK layering

Date: 2026-10-13. Status: proposed.

## Problem and boundaries

Every contract operation declares its execution policy in `x-postgrip-*`
annotations: auth lane, safety, retry, idempotency, pagination and signing.
The generators emit an operation table per plane, but hand-written code reads
it inconsistently:

- Go Service retries when `Retry == "bounded"` and the operation is read-only
  or carries an `Idempotency-Key`. Worker adapters in all three languages decide
  from the HTTP method instead. Agent adapters never retry, and no language
  passes the root retry opt-in to the Agent plane.
- Retry/backoff, `Retry-After` parsing, error-envelope decoding and
  idempotency-key validation are copied into both Worker and Service in every
  language (`go/{worker,service}/client.go`, `typescript/src/{worker,service}/client.ts`,
  `python/src/postgrip/{worker,service}/client.py`; Python also copies its
  cancellation-aware connection classes). The copies have diverged: only
  Service bounds `Retry-After` and exposes retry ceilings.
- Worker and Service failures are typed errors carrying code, message,
  request ID and details. Agent failures are not: Go `SDKError` holds a status
  and raw body, TypeScript throws a bare `Error`, Python a bare `RuntimeError`.
- Caller-supplied headers are copied before the auth lane is applied, so an
  `Authorization` header configured on an Agent connection reaches the
  public session-refresh route in all three languages. This conflicts with
  [architecture](../development/architecture.md): never route a management
  token to a public refresh endpoint.
- Go and Python bound ordinary requests at 30 seconds; TypeScript has no
  request timeout, contrary to the common timeout in [configuration](../configuration.md).

Baseline: SDK `0ea34791`, contract bundle
`a7d0c48055260f5fbf599cc94ea78f07d5f35866ce1aa8718338bb6696b69010`, Agent 45,
Worker 13 and Service 123 operations. The mirrors match web `origin/main`
byte-for-byte, and generator, drift, coverage, recorded endpoint and cURL
checks pass. Annotation census: Agent marks 18 read-only GETs `bounded` and
27 operations `none`; every Worker and Service operation is `bounded`, and
every Worker and Service mutation or destructive operation requires
idempotency.

This design covers how generated HTTP operations execute in all three
languages. Contracts, wire types, `agent-task-v1` signing bytes, WebSocket and
archive framing, and workflow runtime semantics do not change. Follow
[contracts](../development/contracts.md) and [validation](../development/testing.md).

## Target layering

Each language uses the same five layers. Dependencies point downward only:

1. **Generated plane modules**: schema types, the operation table and thin
   typed operation functions over an executor interface. They import only
   standard libraries and the shared transport's operation types.
2. **Shared transport** in `go/internal/transport`, `typescript/src/internal`
   and `python/src/postgrip/_internal`: one executor, retry policy, error type
   and cursor paging. It imports no plane.
3. **Runtime adapters**: Agent signing, session refresh, long polling,
   WebSocket relay, archive streams and log followers. They wrap the executor
   through hooks and never re-implement request execution.
4. **Plane clients**: idiomatic list/get/page/iterate methods built from
   generated operations and generated or protocol types, never from ad-hoc
   payload maps.
5. **Root facade**: composes planes and passes common configuration
   (timeout, retries, insecure development, HTTP client) to every plane,
   Agent included.

Planes never import the root or another plane. Protocol mirrors sit beside
layer 1 and continue to follow [contracts](../development/contracts.md).

## Executor contract

The executor takes one operation's table entry, path parameters, query, body
and per-call options, then applies the contract in this order:

1. **Route.** Join the validated plane base URL and the percent-encoded path.
2. **Credentials by auth lane.** `public` sends no `Authorization` and
   removes any caller-supplied one, case-insensitively. `management`,
   `worker-management` and `service-management` send the management bearer;
   an explicit caller header keeps its current precedence on these lanes.
   `agent` sends only the delegated session from the Agent adapter's credential
   hook. `either` prefers the delegated session, else the management bearer.
3. **Signing.** When the operation requires signing, call the adapter's
   signer hook on the final request. The executor never holds the key.
4. **Idempotency and preconditions.** When idempotency is `required`, reject
   a missing or invalid key before sending, and reuse the same key and body on
   every attempt. Forward `If-Match` only where the operation declares it.
5. **Lifetime.** Bound each ordinary exchange at 30 seconds by default in every
   language; an earlier caller deadline, context or `AbortSignal` wins.
   Streaming requests keep their adapter-owned lifetime.
6. **Redirects.** Apply the plane's configured redirect policy. Each plane
   keeps its current policy in each language: Go follows same-origin
   redirects; TypeScript uses `redirect: 'manual'`; Python Agent follows
   same-origin redirects, while Python Worker and Service follow none and
   return every 3xx as an error. Unifying these needs its own design.
7. **Retry.** Only when retries are enabled, `Retry == "bounded"`, and the
   operation is read-only or carries an idempotency key. Use the status set
   Service retries today, honor `Retry-After` up to the plane ceiling, and use
   jittered backoff. Never retry `protocol` operations, signed requests,
   streaming uploads or WebSocket operations, even if mis-annotated.
8. **Response.** Read the body within the operation's size bound: the plane
   default, unless the plane configuration names a per-operation override.
   Service keeps its 4 MiB default and the 24 MiB `getServiceDeploymentScreenshot`
   exception in all three languages.
9. **Accepted statuses.** An operation may declare non-2xx statuses that its
   adapter handles. For those, the executor returns the bounded raw response
   to the adapter and skips envelope decoding. `pollAgentTask` declares 410:
   the long-poll adapter keeps parsing that body as a `PollTaskResponse`
   shutdown directive, as all three transports do today.
10. **Errors.** Decode the common envelope into one base error carrying status,
    code, message, request ID (falling back to `X-Request-ID`), details and
    retry-after. Default error text comes from a per-plane formatter. Worker
    and Service keep their current text, including the decoded envelope
    message. Agent text contains method, route, status and code only, never
    server-provided content, as in the [Go error-body design](go-agent-http-error-bodies.md).

Plane differences are configuration, not copies: error-type naming and text
formatter, retry ceilings, the `Retry-After` cap, redirect policy, response
size bounds with per-operation overrides, accepted statuses and credential
hooks.

## Per-language shape

**Go.** `go/internal/transport` gains `Operation`, `Executor`, `RetryPolicy`
and `APIError`. The generator emits `transport.Operation` values, adding the
idempotency and pagination annotations the current table omits. `worker.APIError`
and `service.APIError` remain distinct named types that embed or wrap the
shared type, never type aliases. An alias would make both planes one type, so
`errors.As` with a `*worker.APIError` target would match Service errors too. Agent `SDKError` keeps
`StatusCode` and `ResponseBody` and gains `Code`, `RequestID` and `Details`.
`ConnectionOptions` gains the opt-in retry setting, which `postgrip.New`
passes through.

**TypeScript.** `src/internal/transport.ts` exports the executor and
`PostGripAPIError`. `WorkerAPIError` and `ServiceAPIError` extend it, and a
new `AgentAPIError` replaces bare `Error`. Root and plane configs gain
`timeoutMs`, defaulting to 30000, combined with the caller's `AbortSignal`.
Entry points keep explicit named exports.

**Python.** `_internal/transport.py` holds the executor over the existing
`_internal/http.py`, plus the single copy of the cancellation-aware connection
classes. Its opener takes the redirect policy as configuration: no-redirect
for Worker and Service, and the existing same-origin handler for Agent. `PostGripAPIError` carries `status`, `code`, `message`, `request_id`
and `details`; `WorkerAPIError` and `ServiceAPIError` subclass it. Agent
raises `AgentAPIError(PostGripAPIError, RuntimeError)` so existing
`except RuntimeError` handlers still match. Async clients keep wrapping the
synchronous executor.

## Compatibility

No published API is removed. Retries stay opt-in. With default
configuration, requests are unchanged except for three observable changes:

- TypeScript requests gain a 30-second default timeout.
- Public-lane requests drop caller-supplied `Authorization`.
- TypeScript and Python Agent failures become typed errors whose default text
  omits server-provided content, matching Go.

Worker and Service error text, redirect handling, response size bounds and
410 poll handling stay as they are.

Worker retry behavior does not change: for its annotations, the contract rule
selects the same operations as the method rule. With retries enabled, the 18
`bounded` Agent reads become retryable. Generated output changes only through
`scripts/generate_openapi.py`.

## Delivery slices

1. Go shared executor and error type, generator table change and the Worker
   move, with the executor conformance test. State the layering rule in
   [architecture](../development/architecture.md).
2. Go Service onto the executor, removing its private copies.
3. Go Agent onto the executor: lane enforcement, envelope errors and opt-in
   retry wired from the root.
4. TypeScript executor, timeout, error hierarchy and the three plane moves.
5. Python executor, error hierarchy and the three plane moves.
6. Extend `scripts/check_package_layout.py` from root-import checks to an
   allowed-edge matrix: no plane-to-plane, generated-to-adapter or
   transport-to-plane imports. Prove each rule with generic self-test fixtures,
   and point the architecture guide at the checker.

Each slice is its own PR under the [review process](../development/contributing.md).
A slice that changes current behavior updates its owner in the same PR, so
owners never describe obsolete behavior between merges. For example, slice 3
updates [configuration](../configuration.md) for Agent retry and
[authentication](../authentication.md) for Agent error fields, and slice 4
updates configuration for the TypeScript timeout. The design never stands in
for an owner.
Separate designs cover generating the TypeScript and Python protocol mirrors
with a shared `agent-task-v1` signing vector, workflow suspension and replay
defects, delegated runtime credentials picked up by root facades, and recorded
coverage of `connectSandboxSession`.

## Acceptance

For each language, a table-driven test runs all of that language's generated
operations against a local recording server. It asserts:

- per-lane headers, including no `Authorization` on public routes when the
  caller configured one;
- retry eligibility with retries enabled and disabled;
- a required key is rejected when missing and reused across attempts;
- `If-Match` is forwarded only where declared;
- envelope fields decode, and each plane's default text matches its formatter;
- per-plane redirect policy is unchanged, including Python Worker and Service
  returning a 3xx without following it;
- Service response bounds, including a screenshot over 4 MiB that is accepted
  and an ordinary response over 4 MiB that is rejected;
- `pollAgentTask` 410 responses with empty, malformed and populated bodies
  still reach the long-poll adapter as shutdown directives;
- Go `errors.As` with a Worker target does not match a Service error;
- the default timeout and caller deadline precedence.

Existing plane tests, the recorded endpoint and cURL runners, generator and
drift checks, the package-layout checker and strict documentation builds pass
unchanged apart from the intended changes listed under Compatibility.
