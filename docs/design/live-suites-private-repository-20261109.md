# Live suites from a private repository

## Problem

This repository became public on 2026-11-09 (audit log `repo.access`, 00:03
UTC, `private` to `public`). Its stage live suites stopped working:

- GitHub doesn't let a public repository use actions or reusable workflows
  from a private one, whatever the private repository's access setting. The
  nightly's lease and Agent steps use web's `stage-lease` and
  `disposable-agent` actions, so run 42546891851 failed at job setup with
  `Unable to resolve action postgrip-io/postgrip-web, not found`.
- The `mediumworx` runner group, which is the only one that reaches the stage
  host's LAN, didn't allow public repositories, so the same run first sat
  queued with no runner. The group now allows them, temporarily, so the run
  could be diagnosed. A public repository on runners inside the stage LAN
  is a standing risk: the fork pull request approval policy is the only
  thing that keeps an outside contributor's workflow off them.
- Every publishing workflow (`publish-go.yml`, `publish-python.yml`,
  `publish-typescript.yml`) calls `live-pre-release.yml` before it
  publishes, so no SDK release can pass its gate either.

Web's CLI releases also read this repository's nightly and pre-release runs
as release evidence (web `scripts/ci/release-evidence-model.mjs`, kinds
`sdk-nightly` and `sdk-pre-release`), matching each run's `head_sha` to the
SDK commit.

## Decisions

### D1. A private repository runs the stage suites

`postgrip-io/postgrip-sdk-live` (private) owns the nightly and pre-release
workflows and their protected environments. It holds workflow wiring only:

- Each job checks out `postgrip-io/postgrip-sdk` at the commit under test,
  which needs no token because this repository is public, and runs that
  checkout's own scripts (`scripts/test_live_api.py`,
  `scripts/test_github_adoption_live.py`,
  `scripts/test_service_domain_verification_live.py`). The fixture manager,
  scenario schema, operation ownership and their tests stay here, with one
  owner.
- The nightly runs on a schedule and on `workflow_dispatch`, testing this
  repository's `main` as resolved once when the run starts, so every job
  tests the same commit. The pre-release takes a required `sdk-sha` input
  (a full 40-character SHA).
- Jobs keep [live-suites D1](live-suites-on-stage-20261017.md#d1-runners-lease-and-shell):
  the `mediumworx` group, the stage lease jobs, web's actions pinned by
  commit, `shell: bash`, and the same timeouts. A private repository may use
  web's actions because web shares them with the organization.
- The lease run ID stays `<repository id>-<run id>-<attempt>`, now with the
  private repository's ID.

This repository then has no workflow on self-hosted runners. After the first
passing nightly from the private repository, the `mediumworx` group goes back
to refusing public repositories.

### D2. Environments move with the workflows

`sdk-live-nightly` and `sdk-live-pre-release` are recreated in the private
repository, with the same variables and secrets, restricted to its `main`
branch. Variables are copied through the API. Secret values can't be read
back, so they are set again from the files on the stage host, as
[live-suites D2](live-suites-on-stage-20261017.md#d2-environments-and-credentials)
describes, piped into `gh secret set` so no value appears in argv, logs or
chat. This repository's two environments are deleted after the first passing
nightly from the private repository, so no stage credential remains in a
public repository.

### D3. The private run reports a commit status on the SDK commit

Each suite run sets a commit status on the SDK commit it tested:
`postgrip-sdk-live/nightly` or `postgrip-sdk-live/pre-release`. It is
`pending` when the run starts, then `success` or `failure`. Its
`target_url` is the private run, which only organization members can open,
and its description names no stage value.

The status token is a fine-grained token with **Commit statuses: write** on
`postgrip-io/postgrip-sdk` only, stored as `SDK_COMMIT_STATUS_TOKEN` in both
private environments. It can't push, read secrets or change workflows here.
A GitHub App installation token may replace it later; the context names
don't change.

A status is only as trustworthy as the set of writers. People with write
access to this repository can also set these contexts, and could point one
commit's status at a genuine run that tested another commit. So the run
records the commit it tested where only the run can write it: the job that
resolves the SDK commit uploads an empty artifact named
`sdk-commit-<sha>`. Each run has exactly one. A consumer accepts a status
only after checking the linked run itself, including that marker, as
[accepting a run](#accepting-a-run) describes.

#### Accepting a run

A run proves that SDK commit `C` passed tier `T` when all of these hold:

1. the `postgrip-sdk-live/T` status on `C` is `success`, and its
   `target_url` is `https://github.com/postgrip-io/postgrip-sdk-live/actions/runs/<id>`;
2. run `<id>` is in `postgrip-io/postgrip-sdk-live`, its path is
   `.github/workflows/live-T.yml`, and it completed with conclusion `success`;
3. its artifacts include exactly one named `sdk-commit-<sha>`, and `<sha>` is
   `C`.

The marker's name comes from the same job output that every checkout uses,
and only the private repository's `main` can change that wiring.

### D4. Publishing waits for a passing pre-release status

Each publishing workflow replaces its reusable `live-pre-release.yml` call
with a `pre-release-live` job on a GitHub-hosted runner. It runs in a new
`sdk-release-gate` environment, restricted to release tags, which holds
`SDK_LIVE_DISPATCH_TOKEN`: a fine-grained token with **Actions: write** on
`postgrip-io/postgrip-sdk-live` only. The job:

1. reads `postgrip-sdk-live/pre-release` for `github.sha`;
2. if the run it links is accepted for `github.sha` (D3,
   [accepting a run](#accepting-a-run)), passes;
3. if it is absent or `failure`, dispatches `live-pre-release.yml` with
   `sdk-sha: github.sha`;
4. waits for the status to settle, then applies step 2's check to the result.

A pre-release run that finds an accepted run for its own `sdk-sha` exits
without taking the lease.

The three publishing workflows start together on one tag. The private
workflow's concurrency group is per `sdk-sha`, without cancellation, so at
most one run executes and one waits; a run that finds the status already
`success` at its start exits without taking the lease. The wait job's bound
is 360 minutes, GitHub's limit for hosted runners. A pre-release that waits
longer for the lease (its bound is 690 minutes) leaves the gate failed, and
re-running the publishing job resumes at step 1 without starting a second
suite run.

### D5. Web's release evidence follows the status

Web's `sdk-nightly` and `sdk-pre-release` evidence reads the status on the
SDK commit and accepts the linked run as D3's
[accepting a run](#accepting-a-run) describes, then checks the required jobs
and artifacts as today. The run's `head_sha` is the private repository's
commit, so the `sdk-commit-<sha>` marker replaces the `head_sha`
comparison. That change is web's, in its own pull request.

## Slices

1. This design.
2. The private repository: workflows, environments, and a passing nightly
   (D1 to D3).
3. Web's release evidence (D5).
4. This repository: the publishing gate, removing `live-nightly.yml` and
   `live-pre-release.yml` and their environments, and updating
   [live testing](../live-testing.md), [releasing](../releasing.md) and
   [validation and CI](../development/testing.md) (D1, D2, D4).
5. The `mediumworx` group refuses public repositories again (D1).

Until slice 4 merges, no SDK release can pass its gate. Until slice 3 merges,
web can't use SDK evidence from the private repository.

## Open gaps

- Fine-grained tokens expire. Expiry fails the gate or the status update
  loudly, and the fix is rotation; a GitHub App would remove expiry.
- Statuses can be set by anyone with write access here (D3); consumers
  accept only a linked run whose marker names the same commit. Anyone who
  can change the private repository's `main` can change what it tests, as
  anyone who can change this repository's workflows could before.
- The production smoke stays in this repository: it runs on a GitHub-hosted
  runner and uses no private action.
