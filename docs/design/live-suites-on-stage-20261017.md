# Live suites on the stage environment

## Problem

The SDK's `live-nightly.yml` and `live-pre-release.yml` have no environment
to run against. `sdk-live-nightly` has no variables or secrets, so its `live`
job fails every day at `provide exactly one of --scenario, ...`, and
`sdk-live-pre-release` doesn't exist. Web's CLI releases need a passing run of
each as release evidence (`sdk-nightly`, `sdk-pre-release` in web's
`scripts/ci/release-evidence-model.mjs`).

Web now runs its six live suites on a disposable stage environment
(`www.postgrip.app`, host `intelnuc07`), serialized and reset by a host lease.
See web's [stage environment design](https://github.com/postgrip-io/postgrip-web/blob/main/docs/design/stage-environment-design-20261016.md),
D5 to D7. Step 5 of that design leaves the SDK scenarios, and moving these
workflows onto stage, to this repository.

The workflows also hide one failure today. Each `github-adoption` step runs
`python3 … | tee receipt.json` with the default `bash -e` shell, which has no
`pipefail`. On 2026-10-17 the script exited 1
(`POSTGRIP_GITHUB_LIVE_DISPOSABLE=true is required`) and the job still
succeeded.

## Decisions

### D1. Runners, lease and shell

- Every live job runs on the self-hosted `mediumworx` group
  (`[self-hosted, linux, x64]`), like web's live suites. GitHub-hosted runners
  can't reach the lease on the stage host's LAN. The group must include this
  repository, which is an organization setting.
- Each workflow takes the stage lease in an `acquire-stage` job before its
  live jobs, starts it in each live job, and releases it in an `always()`
  `release-stage` job after them, so the jobs share one reset. The lease steps
  call web's `.github/actions/stage-lease`, pinned by commit, so the lease
  protocol has one owner. That needs `postgrip-web`'s Actions access set to
  allow repositories in the organization.
- Jobs default to `shell: bash` (`-eo pipefail`), so a failing script before
  `| tee` fails its step.

### D2. Environments and credentials

`sdk-live-nightly` (restricted to `main`) and `sdk-live-pre-release`
(restricted to the refs that call it: release tags and `main`) are filled from
the files on the stage host, as web's suites are, so no value appears in argv,
logs or chat:

- `POSTGRIP_URL`, `POSTGRIP_AGENT_URL`, `POSTGRIP_WORKER_URL` and
  `POSTGRIP_SERVICE_URL` name the stage hostnames. `POSTGRIP_LIVE_DISPOSABLE`
  and `POSTGRIP_GITHUB_LIVE_DISPOSABLE` are `true`.
- `POSTGRIP_TOKEN` is a stage management token per environment covering the
  three planes (web D5). Its exact scopes are the minimum the scenario's
  operations need, and are recorded with the scenario. It is minted under a
  stage maintenance lease and captured into the stage baseline, and the
  stage's reset validation checks it on its planes.
- The pre-release Agent session (`POSTGRIP_AGENT_ID`, access and refresh
  tokens, signing key) belongs to an Agent enrolled on stage and captured in
  the baseline. A run's refresh rotates that session, but the next run's
  reset restores the baseline, so the stored session is valid again at the
  start of every run.
- The live fixtures (`POSTGRIP_LIVE_WORKER_ID`, repository and sandbox image)
  name stage objects that the baseline keeps: the long-lived stage Worker, a
  repository in the stage GitHub organization, and a public image.
- GitHub adoption needs `POSTGRIP_GITHUB_LIVE_PROJECT_ID` (a stage project
  whose production environment is assigned to the stage Worker, captured in
  the baseline), `POSTGRIP_GITHUB_TEST_ORG` and `POSTGRIP_GITHUB_TEST_TOKEN`.
  The adoption test creates repositories, so the stage GitHub App
  installation in that organization must cover all its repositories.

### D3. Scenarios

Each tier's scenario follows `test/live-scenario.schema.json` and the existing
fixture-manager rules. The nightly scenario holds the 132 nightly operations
and the pre-release scenario the 47 pre-release operations from
`test/operation-tests.json`. Both are kept on the stage host
(`~/.config/postgrip-stage/sdk-live-<tier>.json`, mode 600) and loaded into
`POSTGRIP_LIVE_SCENARIO_GZIP_BASE64`. They are checked with
`--validate-only` before each upload.

### D4. Delivery

1. This design.
2. Workflows: runners, lease jobs and shell (D1). Until the environments are
   filled, the live jobs fail at configuration, as they do today, but the
   adoption job no longer reports success.
3. Stage configuration and environments (D2), under a maintenance lease.
4. Nightly scenario, until `live-nightly.yml` passes end to end.
5. Pre-release scenario, until `live-pre-release.yml` passes end to end.

Each run counts as web release evidence only when the whole workflow succeeds,
including `release-stage`.

## Validation

- `scripts/test_live_api.py --self-test` and
  `scripts/test_github_adoption_live.py --self-test` pass, as today.
- A misconfigured adoption job fails its run.
- Two live workflows started together, from this repository or from web, run
  one after the other on stage.
- `live-nightly.yml` and `live-pre-release.yml` each pass once on stage with
  their ledgers showing no remaining resources, and validate through web's
  `verify-release-evidence.mjs` as `sdk-nightly` and `sdk-pre-release`.
