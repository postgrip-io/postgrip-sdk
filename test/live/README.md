# Live API scenarios

The live suites execute the unified Python SDK against a real PostGrip
environment. Recorded conformance remains the exhaustive cross-language PR
gate; live scenarios prove deployed semantics, resource lifecycles, runtime
signing, archives, logs, cancellation, and WebSocket behavior.

Environment-specific scenarios are secrets because they may name disposable
workers, repositories, images, and host-runtime fixtures. They must validate
against `test/live-scenario.schema.json` and contain every operation assigned
to their tier in `test/operation-tests.json` exactly once. A scenario can be
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
