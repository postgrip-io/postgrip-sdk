# Live API scenarios

The live suites execute the unified Python SDK against a real PostGrip
environment. Recorded conformance remains the exhaustive cross-language PR
gate; live scenarios prove deployed semantics, resource lifecycles, runtime
signing, archives, logs, cancellation, and WebSocket behavior.

Environment-specific scenarios are secrets because they may name disposable
workers, repositories, images, and host-runtime fixtures. They must validate
against `test/live-scenario.schema.json`, and their counted steps must contain
every operation assigned to their tier in `test/operation-tests.json` exactly
once. Fixture and wait steps (below) don't count toward that set. A scenario can be
provided as `POSTGRIP_LIVE_SCENARIO_JSON` or as a gzip-compressed base64 value
in `POSTGRIP_LIVE_SCENARIO_GZIP_BASE64`.

## Resource ownership

`${runPrefix}` and `${runId}` are generated for each invocation. Captured
response values use `${var.name}`; deployment values use
`${env.POSTGRIP_LIVE_NAME}`. Environment substitutions are deliberately
limited to `POSTGRIP_*` names.

Every mutation must either declare `createsResource` or target a registered
`resourceKey`. Resource names must contain `${runPrefix}`. The manager stores
only operation results and explicit resource identifiers in its mode-0600
ledger—never tokens, headers, bodies, or captured secrets. Cleanup operations
run in reverse registration order and may not contain wildcard path values.
For targeted mutation, destructive, and protocol steps, the resolved path
parameters must contain the exact identifier recorded for `resourceKey`;
naming a ledger entry while the target path names another object is rejected
before network execution. Cleanup requests are resolved and frozen when a
resource is registered. Creation intent is written before the request, and the
identifier plus cleanup are finalized before processing non-resource response
captures.

Destructive operations and destructive cleanup require all three controls:

1. `disposableEnvironment` is `true` in the scenario;
2. `POSTGRIP_LIVE_DISPOSABLE=true` is set by the protected environment;
3. the runner receives `--allow-destructive`.

If an operation and cleanup both fail, the report preserves the original
failure, reports cleanup failures separately, and lists every remaining
identifier.

## Step modes

These follow the [live-suites design](../../docs/design/live-suites-on-stage-20261017.md),
D3 and D3a. The production smoke tier accepts none of them.

- **Fixture steps** (`"fixture": true`) set up a prerequisite. They may name
  any operation, of any tier, any number of times, and are held to every
  safety, resource, cleanup and destructive rule a counted step is.
- **Wait steps** (`"wait": {"capture", "equals", "intervalSeconds",
  "timeoutSeconds"}`) repeat one read-only operation until the named capture
  equals `equals` (JSON equality, after placeholder resolution). The interval
  is 1 to 60 seconds and the total time 1 to 1800. No poll starts after the
  total time has passed, so a wait ends within it plus the poll already in
  flight, which the SDK's 30-second request timeout bounds. A timeout fails
  the step with the attempt count and the last observed value. A wait step can't create or clean resources,
  and its captures come from the matching response.
- **Credential steps** (`"rotatesCredentials": true`) name an operation that
  accepts an Agent refresh token, such as `refreshAgentSession`, with an empty
  request and no captures, resource or cleanup. The runner's adapter sends its
  Agent connection's current refresh token and applies the returned access and
  refresh tokens to that connection for later steps. The tokens stay in the
  adapter: they never reach captures, the ledger, or the report, and are
  redacted from failures. Any step naming such an operation must be a
  credential step.

Only steps with neither `fixture: true` nor `wait` count toward coverage. A
credential step is counted unless it's also a fixture step.

## Resource lifecycles

A created resource's `lifecycle` defaults to `cleanup`. Seeded resources must
use it. The other two lifecycles record only the identifier, take
`"cleanup": null`, and are never reported as remaining:

- **`transient`**: a resource that the server spends or expires, such as a
  sandbox session. At most one later step may target it, and it must be a
  protocol step, whose resolved path must contain its identifier. The ledger
  reports it as `consumed`, or `expired` if no step consumed it. A transient
  resource's request may omit the run-prefixed name only when its step
  targets a recorded parent resource, which carries the run's attribution.
- **`reset-owned`**: a resource that has no delete route, such as a namespace.
  The ledger reports it as `left-for-stage-reset`. The runner accepts one only
  when `POSTGRIP_LIVE_STAGE_LEASE` names the stage-lease run ID (letters,
  digits, `.`, `_`, `:` or `-`, up to 128 characters), the scenario sets
  `disposableEnvironment`, and `POSTGRIP_LIVE_DISPOSABLE=true`. Otherwise it
  refuses the scenario before any request. The nightly and pre-release `live`
  jobs set it to the run's lease ID, and each job's scenario runs only after
  its lease `start` step succeeds. The lease's release resets stage, which
  removes these resources. `--validate-only` doesn't need it.

No step may clean a transient or reset-owned resource.

## Cleanup precondition refresh

Fenced deletes need values that exist only just before deletion, such as a
current `If-Match` ETag or a removal preview's `impactHash`. A cleanup may
declare a `refresh`:

```json
"cleanup": {
  "operationId": "deleteServiceEnvironment",
  "request": {"pathParameters": {"...": "..."}, "query": {}, "headers": {},
              "body": {}, "streamBodyBase64": null},
  "refresh": {
    "operationId": "getServiceEnvironment",
    "request": {"pathParameters": {"...": "..."}, "query": {}, "headers": {},
                "body": null, "streamBodyBase64": null},
    "headers": {"If-Match": "/etag"},
    "body": {"/impactHash": "/impactHash"}
  }
}
```

The refresh operation must be read-only. The runner resolves and freezes it
with the cleanup when the resource is registered, and runs it just before the
cleanup. `headers` maps a header name to a JSON pointer into the refresh
response. `body` maps a JSON pointer in the cleanup body, which must be an
object, to one in the response. Each value must be a scalar, and credential
headers can't be filled. Path parameters and the query, which select the
target, stay frozen. If the refresh fails, the cleanup doesn't run and the
resource remains. A step that cleans the resource explicitly must match the
frozen cleanup, except for its declared precondition fields.

## Ledger

Each resource row records its `lifecycle` and `outcome` (`cleaned`,
`remaining`, `consumed`, `expired` or `left-for-stage-reset`). The ledger lists
`remainingIdentifiers`, `consumedIdentifiers`, `expiredIdentifiers` and
`stageResetIdentifiers`, and records the run's `stageLease`. Each operation
row records its `role`: `counted`, `fixture` or `wait`.

## Commands

Validate safety and cleanup behavior without network access:

```sh
PYTHONPATH=python/src python3 scripts/test_live_api.py --self-test
```

Validate a deployment scenario without executing it:

```sh
python3 scripts/test_live_api.py \
  --tier nightly \
  --scenario /secure/nightly.json \
  --validate-only
```

The scheduled and release workflows install the built Python distribution,
load scenario data from their protected GitHub Environment, and upload the
cleanup ledger even when the run fails.

## GitHub App adoption lifecycle

The same workflows run `scripts/test_github_adoption_live.py` as a separate,
strict job. It creates one private repository in a dedicated GitHub test
organization, waits for PostGrip discovery, previews and executes adoption,
observes a signed push event queue an automatic deployment, performs two
explicit credential rotations, and deletes the repository in a `finally`
cleanup path. The pre-release lane waits 65 minutes before its push so the
original GitHub installation token would be rejected; a successful queued
deployment therefore proves background rotation kept Worker access usable.

The protected `sdk-live-nightly` and `sdk-live-pre-release` environments must
provide:

- `POSTGRIP_GITHUB_LIVE_PROJECT_ID`: a dedicated, non-production project with
  a production environment assigned to an online Worker;
- `POSTGRIP_GITHUB_TEST_ORG`: a dedicated test organization whose PostGrip
  GitHub App installation is authorized for all repositories, so newly created
  disposable repositories are visible;
- `POSTGRIP_GITHUB_TEST_TOKEN`: a least-privilege test credential allowed only
  to create and delete repositories in that organization; and
- `POSTGRIP_GITHUB_LIVE_DISPOSABLE=true`.

The GitHub credential belongs only to the external fixture manager. It is
never sent to PostGrip, written to a scenario or ledger, or printed. Production
PostGrip organizations are rejected by the runner. Validate the destructive
guards without network access with:

```sh
python3 scripts/test_github_adoption_live.py --self-test
```
