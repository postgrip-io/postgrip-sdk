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
  that job's start (postgrip-io/postgrip-web#2200). The live jobs, `live`,
  `github-adoption` and `service-domain`, all start once `acquire-stage`
  holds the lease, and run in parallel. The nightly scenario puts
  `stage-worker` into maintenance and upgrades it, so the adoption job deploys
  to `stage-worker-2`, which no scenario puts into maintenance or upgrades.
  Neither adoption job waits for the original installation token to expire
  (decided 2026-10-18, to keep runs short), so neither proves rotation after
  expiry; the suite still supports that wait. Because each job renews the
  lease when it starts, the window must outlast the longest single job:
  `live`, at 120 minutes for nightly and 135 for pre-release. Web raises the active window from 90 to 150 minutes, and
  caps a run's whole active hold at 5 hours from its first `start`, because
  each job renews the window (postgrip-io/postgrip-web#2201). Every
  `acquire-stage` bound is 690 minutes, so a waiting run outlasts one
  predecessor's whole hold: its 6-hour claim, its capped active hold and its
  reset. The lease steps call web's
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
- Each run provides its own Agents through web's `disposable-agent` action,
  pinned by commit
  ([web design](https://github.com/postgrip-io/postgrip-web/blob/main/docs/design/stage-disposable-agent-action-design-20261018.md)).
  Stage keeps no long-lived Agent, whose local state a reset would leave
  behind the restored database.
  - Its `up` step, in the `live` job before the scenario, runs a
    sandbox-capable Agent on the runner for the sandbox lifecycle.
  - It also enrolls a headless scenario identity limited to the scenario's
    namespace and queues. Only the pre-release job maps its session and
    signing key into the scenario step, as `POSTGRIP_AGENT_ID`, the access
    and refresh tokens, the expiry and `POSTGRIP_AGENT_SIGNING_PRIVATE_KEY`.
    The nightly job maps none of them, so the nightly tier keeps no Agent
    session (D3a's reset-owned tasks rely on that).
  - The session reaches the scenario step as masked step outputs. GitHub
    passes those through the runner's per-step `GITHUB_OUTPUT` file in the
    job's temporary directory, which the runner empties when the job ends;
    nothing else writes them to disk. The session expires on its own, and
    `down` deletes the identity, so no session is stored on stage or renewed.
  - Its `down` step (`always()`) tears down every sandbox the sandbox Agent
    was assigned before it removes either Agent. Sandbox deletion is
    asynchronous (`deleteSandbox` returns 202 and the Agent finishes it), so
    `down` doesn't wait on the Agent: it stops the Agent, lists that Agent's
    sandboxes, removes each one's containers by its own sandbox label, and
    deletes the private directory holding their local state. Then it revokes
    both enrollment keys and deletes both Agents.
  - The scenario's queues differ from the ones the sandbox Agent polls.
  - Enrollment keys can only be issued by an owner or admin session, so both
    environments hold the stage owner's email and password
    (`STAGE_OWNER_EMAIL`, `STAGE_OWNER_PASSWORD` secrets) and the stage
    organization (`STAGE_ORGANIZATION_ID`), used only by that action (web
    stage design D5).
  - Each run names the action's run `sdk-<run_id>-<attempt>`, and the
    identity's namespace and queue after it. The scenario step reads them as
    `POSTGRIP_LIVE_AGENT_NAMESPACE` and `POSTGRIP_LIVE_AGENT_QUEUE`.
  - Using the identity's own session instead of a delegated one is a
    stage-test decision; customer workloads still get delegated sessions
    (`docs/authentication.md`).
- The live fixtures (`POSTGRIP_LIVE_WORKER_ID`, repository and sandbox image)
  name stage objects that the baseline keeps: the long-lived stage Worker, a
  repository in the stage GitHub organization, and a public image.
- The pre-release scenario also reads the second stage Worker, the branch
  and the domain suffix, and two Worker bootstrap values for `createWorker`.
  The `live` job generates those two per run (32 random bytes each, unpadded
  base64url) and masks them before the scenario starts. Its waits need a
  135-minute job, inside the lease's 150-minute window.
- Pre-release also needs three more baseline objects, named by environment
  variables: a DNS domain with published records
  (`POSTGRIP_LIVE_DNS_{PROJECT,ENVIRONMENT,DOMAIN}_ID`), a failed stack
  operation (`POSTGRIP_LIVE_FAILED_STACK_{KEY,OPERATION_ID}`) and a
  secret-blocked one (`POSTGRIP_LIVE_SECRET_STACK_{KEY,OPERATION_ID}`). A
  run-created domain can't become active, because its ownership proof must
  be published before the run. The two stack states arise only after
  repeated delivery failures or an expired secret envelope. The scenario's
  steps that need them run last.
- GitHub adoption needs `POSTGRIP_GITHUB_TEST_ORG` and
  `POSTGRIP_GITHUB_TEST_TOKEN`. The adoption test creates repositories, so
  the stage GitHub App installation in that organization must cover all its
  repositories.
  - It needs no baseline project. The job passes the second stage Worker as
    `POSTGRIP_GITHUB_LIVE_WORKER_ID` (D1), and the suite creates a project on its
    disposable repository, with a production environment on that Worker,
    before adopting the repository. The stage reset removes the project.
  - A baseline project can't work. A repository can be adopted into only
    one project, so a project left adopted on a shared fixture blocks web's
    zero-touch suite. An unadopted project's environment never configures on
    stage: it needs a per-repository webhook, which the stage App can't
    register.
  - The environment is created before the adoption, because an adoption
    preview needs an assigned Worker. Its configuration retries until the
    adoption moves the project to the App's global webhook.

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
step is.

Some resources are created to be consumed. A sandbox session from
`createSandboxSession` has its own ID, is spent by `connectSandboxSession`,
and expires on the server, and there is no operation that deletes one. So a
resource can be declared transient: it records its identifier, needs no
cleanup, and may be consumed by exactly one later protocol step that targets
it. The ledger reports it as consumed or expired, never as remaining. It doesn't count toward coverage: the counted steps must still equal
the tier's operations exactly once, so coverage is unchanged. Tier
assignments stay as they are. The nightly scenario covers 135 operations and
the pre-release scenario 50, plus their fixture steps. DNS failover and plan
rollback left the public API on 2026-10-18 (web
`docs/archive/20261018/dns-failover-rollback-removal-20261018.md`), which
removed one nightly and three pre-release operations. Web's recovery move
(`docs/design/worker-refresh-replay-recovery-design-20261101.md`, D5b and
D5c) added three pre-release operations, `getRecoveryMove`,
`reviseRecoveryMoveVolume` and `confirmRecoveryMoveVariables`. They need a
recovery move off a lost stage Worker, so the stage pre-release scenario must
add a lost-Worker fixture and all three steps before `live-pre-release.yml`
can pass again. Web's public Worker snapshots
(`docs/design/public-worker-snapshots-design-20261107.md`) added five:
`getWorkerSnapshotStatus` and `getWorkerSnapshotSettings` (nightly), and
`listWorkerSnapshots`, `createWorkerSnapshot` and
`updateWorkerSnapshotSettings` (pre-release). They need a stage Worker that
advertises `worker_snapshot_api_v1`, and the pre-release three a storage
destination whose credentials the console delivered to it; the settings step
restores the Worker's previous settings. Both stage scenarios must add these
steps before their workflows can pass again
([SDK design](worker-snapshots-20261107.md)). Web's public storage
destinations (`docs/design/public-storage-destinations-design-20261107.md`)
added one nightly read, `listStorageDestinations`. It needs no fixture beyond
the stage organization's token and answers `{"items": []}` for an
organization with none, so the stage nightly scenario must add the step before
`live-nightly.yml` can pass again
([SDK design](worker-storage-destinations-20261107.md)). Web's Agent task
cancel (`docs/design/agent-task-cancel-and-idempotency-design-20261107.md`)
added one nightly mutation, `cancelTask`. It cancels a `noop` task the
scenario enqueued on a queue no Agent polls, so the task is still `queued`;
the stage nightly scenario must add the enqueue and cancel steps before
`live-nightly.yml` can pass again
([SDK design](agent-task-cancel-20261107.md)).

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

### D3a. What a draft nightly scenario showed

Before the 2026-10-18 failover removal, a full nightly scenario was drafted
from the recorded fixtures and checked offline. It passed `--validate-only`,
and a dry run through the fixture manager's own execution rules, against a
fake adapter, got through 124 of its 132 steps. That is historical evidence:
the nightly tier is now 131 operations, so the draft must drop
`getServiceDNSFailoverPolicy` to validate again. A live run still can't pass without three more fixture-manager
capabilities and some stage objects:

- **Precondition refresh for cleanups.** Cleanup requests are frozen at
  registration, which the self-test pins, so a later capture can't redirect a
  delete. But fenced deletes need values that only exist just before
  deletion: the current `If-Match` ETag, and the `impactHash` of a removal
  preview. So a cleanup may declare a read operation that the manager runs
  just before it. Captures from that read fill only the cleanup's declared
  precondition fields, which are headers and body fields. Path parameters,
  and so the target, stay frozen.
- **Wait steps.** Some steps depend on asynchronous work finishing: a sandbox
  reaching `running`, a volume becoming available, a deployment going live. A
  wait step repeats one read-only operation at a bounded interval until a
  declared captured value matches, within a bounded total time, and then
  fails with the last value. Like a fixture step, it doesn't count toward
  coverage.
- **Reset-owned resources.** `createNamespace` creates a namespace that
  has no delete route and never expires. `enqueueTask` creates a task that
  only `pollAgentTask`, with an Agent session, can consume, and the nightly
  tier has no session. Neither is transient, and neither can be cleaned up.
  A resource may be declared reset-owned: it records its identifier, needs
  no cleanup, and the ledger reports it as left for the stage reset, not as
  remaining. The manager accepts reset-owned resources only when the run
  holds a stage lease, whose release restores the baseline and removes them,
  so they can't be left behind anywhere else.
- **Fixture steps** (D3) also cover the target-service operations, which
  need fresh catalog ETags from repeated catalog reads.

The stage baseline also needs objects that a nightly run can't create:

- A second trusted Worker, for the environment-reassignment operations.
- A workspace, a configuration stack and release groups, for their reads.
- DNS plan and verification objects, for their reads.

Promotion needs a source deployment in another environment. Fixture steps
create a staging environment, `deployService` (nightly) deploys to it, and a
wait step waits until that deployment is ready. Then `previewServicePromotion`
and `promoteServiceDeployment` promote it.

### D4. Delivery

1. This design.
2. Workflows: runners, lease jobs, shell and environment policy (D1). Web's
   150-minute active window lands first. Until the environments are
   filled, the live jobs fail at configuration, as they do today, but the
   adoption job no longer reports success.
3. Stage configuration and environments (D2), under a maintenance lease.
4. Fixture-manager fixture steps, transient and reset-owned resources,
   credential steps, precondition refresh for cleanups and wait steps (D3,
   D3a). Then the stage baseline objects (D3a), under a maintenance lease and
   captured.
   Then both `live` jobs call the disposable-agent action, `up` before the
   scenario and `down` with `always()`, and nightly maps the variables its
   scenario reads.
5. Nightly scenario, until `live-nightly.yml` passes end to end.
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
