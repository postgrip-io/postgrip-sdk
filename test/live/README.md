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
For targeted mutation, destructive, and protocol steps, the resolved request
must contain the exact identifier recorded for `resourceKey`; naming a ledger
entry while the path or body targets another object is rejected before network
execution.

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
