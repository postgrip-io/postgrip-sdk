# Configuration

TypeScript and Python root clients resolve each plane URL in this order:

1. An explicit constructor value for that plane.
2. `POSTGRIP_AGENT_URL`, `POSTGRIP_WORKER_URL`, or `POSTGRIP_SERVICE_URL`.
3. The explicit common `baseUrl` / `base_url` constructor value.
4. `POSTGRIP_URL`.

An explicit token takes precedence over `POSTGRIP_TOKEN`. Their environment
factory methods use the same resolver as their constructors.

Go's root `New(Config)` uses explicit plane URLs before `Config.BaseURL` and
requires `Config.Token`; it does not merge root configuration with environment
variables. `NewFromEnv()` loads the common token and common/plane URLs from the
environment, then calls `New`. Keep this constructor difference explicit when
translating examples between languages.

`POSTGRIP_TOKEN` is the only developer-configured management credential.

```sh
export POSTGRIP_URL="https://api.postgrip.io"
export POSTGRIP_TOKEN="pgt_..."
```

Plane overrides are useful for cells, self-hosted routing, and local
integration environments:

```sh
export POSTGRIP_AGENT_URL="https://agents.example.com"
export POSTGRIP_WORKER_URL="https://workers.example.com"
export POSTGRIP_SERVICE_URL="https://services.example.com"
```

Base URLs must use HTTPS, contain no query or fragment, and may include a
reverse-proxy path. Plain HTTP requires the explicit insecure-development
constructor option; it is not enabled by an environment variable. Sandbox
relay overrides follow the same rule: use WSS by default, and permit WS only
when that same insecure-development option is enabled explicitly.

Direct Worker and Service clients expose environment factory methods using
the same plane URL and `POSTGRIP_TOKEN` variables; their ordinary constructors
take explicit configuration. Agent connections also consult the environment
and fall back to the built-in cloud address when no URL is supplied. Direct
plane clients do not import or initialize the root facade or another plane.
See [authentication](authentication.md) for Agent runtime credential selection.

## Timeouts, retries, and idempotency

Go's ordinary HTTP exchanges default to 30 seconds, including when a custom
`http.Client` has a nonpositive timeout. Positive custom client timeouts are
preserved without mutating that client; earlier context deadlines still win.
Agent's `RequestTimeout` configures the ordinary timeout only when no custom
`HTTPClient` is supplied. Workspace uploads use a separate 30-minute deadline
when the call's context has none; an explicit context deadline overrides that
default, including for uploads needing longer. Uploads remain independent of
the ordinary request timeout.

Python's root `timeout` defaults to 30 seconds and is passed to each plane. A
Python Agent long poll's timeout is its `wait_seconds` plus 30 seconds when that
exceeds the configured timeout.
TypeScript bounds each exchange in every plane at 30 seconds by default. The
root `PostGripConfig.timeoutMs` is passed to each plane, and
`WorkerClientConfig.timeoutMs`, `ServiceClientConfig.timeoutMs` and Agent
`ConnectionOptions.timeoutMs` set it per plane, up to the 2,147,483,647 ms timer
limit; an earlier `AbortSignal` abort still wins. A TypeScript Agent long poll's
lifetime is its `wait_seconds` (the contract default of 20 when omitted) plus 30
seconds when that exceeds the timeout. Workspace uploads keep their
adapter-owned lifetime. These APIs do not yet offer one common timeout setting
across languages.

Root retry options reach Worker and Service in every language, Go Agent
through `ConnectionOptions.EnableRetries`, which `postgrip.New` sets from
`Config.EnableRetries`, and TypeScript Agent through
`ConnectionOptions.enableRetries`, which `PostGrip` sets from
`PostGripConfig.enableRetries`, and Python Agent through
`Connection(enable_retries=...)`, which `PostGrip` and `AsyncPostGrip` set from
their `enable_retries`. Agent in every language retries only contract-eligible
operations: annotated bounded reads, never signed runtime actions, protocol
operations or streaming uploads. Each attempt obtains the delegated session
again, so a token that nears expiry during a backoff is refreshed first. When the Go Agent connection creates its own
HTTP client, a long poll's lifetime is its `wait_seconds` (the contract default
of 20 when omitted) plus 30 seconds when that exceeds the request timeout; a
supplied `HTTPClient` keeps its `Timeout` as given. Service, Go Worker and Go Agent
eligibility use generated retry/safety metadata plus an idempotency key for
mutations.
TypeScript and Python Worker and Agent use the same contract metadata.
Retries remain opt-in, with attempt counts bounded by the plane
implementation; delay limits are not yet uniform across planes and languages.
Every plane in every language parses `Retry-After` with the same rules:
`0` or a past date retries without backoff, larger values cap at 30 seconds, and a
signed or fractional value such as `+5` or `1.5` is not valid delta-seconds, so
the jittered backoff applies.
The required contract-driven boundary is specified in
[architecture](development/architecture.md).

Mutations that require idempotency use a fresh
`Idempotency-Key` for each new logical mutation, and reuse that same key and
request on retries or response loss. Worker and Service in every language
reject a missing or invalid key on these operations before sending, including
through their generated low-level clients. Service administration writes may
additionally require the current `If-Match` value; Service in every language
forwards `If-Match` only on operations whose contract declares it.

Do not blindly retry protocol operations, signed Agent runtime mutations,
archive transfers, or WebSocket sessions. Their generated pages name the
dedicated adapter and conformance runner.

## Agent history pagination

Task-event and workflow-history endpoints return stable cursor pages. The
first request fixes a snapshot boundary; later events are intentionally absent
from that cursor chain, so deterministic workflow replay cannot change while
the client follows it. Start a fresh request to observe newly appended events.

`limit` accepts 1 through 500 and defaults to 100. The server may return fewer
items to keep the serialized page below its response bound. `nextCursor` is
opaque, resource-bound, and absent on the last page; never parse, edit, or
reuse it for another task or workflow run.

The convenience methods (`GetTaskEvents`/`GetWorkflowHistory`,
`getTaskEvents`/`getWorkflowHistory`, and
`get_task_events`/`get_workflow_history`) follow every page and assemble the
complete snapshot. Callers with large histories should use the bounded
incremental forms instead:

| Language | One page | Incremental iteration |
| --- | --- | --- |
| Go | `GetTaskEventsPage`, `GetWorkflowHistoryPage` | `WalkTaskEvents`, `WalkWorkflowHistory` |
| TypeScript | `getTaskEventsPage`, `getWorkflowHistoryPage` | `iterateTaskEvents`, `iterateWorkflowHistory` |
| Python | `get_task_events_page`, `get_workflow_history_page` | `iter_task_events`, `iter_workflow_history` |

Every individual Agent response is bounded. Choosing a full-history
convenience method can still grow the caller's aggregate collection; the
iterator/walker APIs keep application memory under caller control.
