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

- Every live and lease job sets `runs-on: {group: mediumworx, labels:
  [self-hosted, linux, x64]}`, like web's live suites. Labels alone don't pin
  a job to the group, and only the group's runners reach the stage host's LAN.
  The group must include this repository, which is an organization setting.
- Each workflow takes the stage lease in an `acquire-stage` job before its
  live jobs, starts it in each live job, and releases it in an `always()`
  `release-stage` job after them, so the jobs share one reset. Every live job
  starts the lease before touching stage, so a job whose run lost the lease
  never runs. The parallel jobs rely on web's `start` succeeding again for the
  run that already holds the active lease, renewing it to a full window from
  that job's start (postgrip-io/postgrip-web#2200). The window must outlast
  the longest live job. That's the pre-release
  `github-adoption` job: it waits 65 minutes for the original installation
  token to expire, then up to about 23 more minutes of bounded waits, within a
  120-minute timeout. Web raises the active window from 90 to 150 minutes, and
  every `acquire-stage` bound from 480 to 540 minutes, so a waiting run still
  outlasts one predecessor's whole hold: its 6-hour claim, 150-minute active
  window and reset. The lease steps call web's
  `.github/actions/stage-lease`, pinned by commit, so the lease protocol has
  one owner. That needs `postgrip-web`'s Actions access set to
  allow repositories in the organization.
- Jobs default to `shell: bash` (`-eo pipefail`), so a failing script before
  `| tee` fails its step.
- No human approval may wait while the lease is held. The live environments
  have no required reviewers, only deployment branch and tag policies, like
  web's live environments. GitHub would ask again for each job that names an
  environment with reviewers, while the lease is held. A release's reviewers
  approve the publishing environments, whose jobs run after the pre-release
  suite has released the lease.

### D2. Environments and credentials

`sdk-live-nightly` (restricted to `main`) and `sdk-live-pre-release`
(restricted to the refs that call it: release tags and `main`) are filled from
the files on the stage host, as web's suites are, so no value appears in argv,
logs or chat:

- `POSTGRIP_URL`, `POSTGRIP_AGENT_URL`, `POSTGRIP_WORKER_URL` and
  `POSTGRIP_SERVICE_URL` name the stage hostnames. `POSTGRIP_LIVE_DISPOSABLE`
  and `POSTGRIP_GITHUB_LIVE_DISPOSABLE` are `true`.
- `POSTGRIP_TOKEN` is a stage management token per environment covering the
  three planes (web D5). Its scopes are the union of what that environment's
  jobs call: the scenario's operations, the adoption job's (for example
  `listServiceDeployments`, `services:read`) and the domain job's. They are
  recorded with the scenario. Authorization is per endpoint, so the other
  Service scopes don't imply a missing one. It is minted under a
  stage maintenance lease and captured into the stage baseline, and the
  stage's reset validation checks it on its planes.
- The pre-release Agent session (`POSTGRIP_AGENT_ID`, access and refresh
  tokens, signing key) belongs to an Agent enrolled on stage and captured in
  the baseline. A run's refresh rotates that session, and the next run's
  reset restores the baseline, so the stored tokens are valid again at the
  start of every run until the session's absolute `refreshExpiresAt`. A
  restore can't extend that, and a management token can't issue a delegated
  session. So before `refreshExpiresAt` is within 14 days, the session is
  renewed by re-enrollment, alongside web D6's baseline rotation: under a
  maintenance lease, restore, have the stage owner issue a one-time
  enrollment key, enroll the Agent with it, write the resulting Agent ID,
  session and signing key into the environment, capture, and release. The
  renewal date is recorded next to the tokens' expiry in the stage runbook.
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
fixture-manager rules, including that a scenario holds exactly its tier's
operations, and each exactly once. Some operations need prerequisites that
other tiers' operations create, sometimes more than once.
`connectSandboxSession` (pre-release) needs a ticket from
`createSandboxSession` on a running sandbox, and both are nightly. Each of
`blockAgentTask`, `completeAgentTask` and `failAgentTask` (pre-release)
releases a task that `pollAgentTask` leased, which needs tasks from
`enqueueTask` (nightly). Tickets are single-use, task leases age, and reset
removes the Worker's workload containers, so neither can live in the baseline.

So the fixture manager adds fixture steps. A step marked `fixture: true` may
name any operation, of any tier and any number of times, to set up a
prerequisite. It is held to every safety, resource and cleanup rule a counted
step is. It doesn't count toward coverage: the counted steps must still equal
the tier's operations exactly once, so coverage is unchanged. Tier
assignments stay as they are. The nightly scenario covers 132 operations and
the pre-release scenario 47, plus their fixture steps.

`refreshAgentSession` (pre-release) rotates the Agent session's own tokens.
It neither targets nor creates a recorded resource, which the fixture manager
requires of every mutation, so the manager supports credential steps. A step
marked as rotating its connection's credentials needs no resource. The
manager sends the current refresh token, applies the returned access and
refresh tokens to its Agent connection for later steps, and never writes them
to the ledger or the report. The self-test covers it. Both are kept on the stage host
(`~/.config/postgrip-stage/sdk-live-<tier>.json`, mode 600) and loaded into
`POSTGRIP_LIVE_SCENARIO_GZIP_BASE64`. They are checked with
`--validate-only` before each upload.

### D4. Delivery

1. This design.
2. Workflows: runners, lease jobs, shell and environment policy (D1). Web's
   150-minute active window lands first. Until the environments are
   filled, the live jobs fail at configuration, as they do today, but the
   adoption job no longer reports success.
3. Stage configuration and environments (D2), under a maintenance lease.
4. Nightly scenario, until `live-nightly.yml` passes end to end.
5. Fixture-manager fixture steps and credential steps (D3).
6. Pre-release scenario, until `live-pre-release.yml` passes end to end.

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
