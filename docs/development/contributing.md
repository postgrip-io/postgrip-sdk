# Contribution and review

Use a living design in `docs/design/` for each change, including documentation.
Keep one concern per PR, branch from `main`, and use Conventional Commit titles.
Never commit or push directly to `main`.

1. Implement the design within the [SDK boundaries](architecture.md). Update
   the design before a justified change of scope; do not silently depart from it.
2. Self-review the diff against the design and current topic owners. Run the
   affected [validation](testing.md), including the runtime drift check. Check
   compatibility in each affected language and [web coordination](contracts.md).
3. Open a PR with the design path and implemented slice, per-area changes,
   affected packages/layers, observable impact, compatibility, linked issues
   and coordinated PRs, and exact validation commands and results.
4. Comment `@codex review`. Validate every finding against code and design;
   architecture violations and design drift count alongside bugs. Reply with
   evidence when rejecting a finding. Fix every valid finding in a commit
   titled `Codex review on #N: …` and explain the fix on the PR.
5. If a round has three or more valid findings, request `@codex review` again
   after fixing them. With two or fewer, fix them and wait for green CI, then
   squash-merge with `gh pr merge --squash --delete-branch`. The squash subject
   is the Conventional Commit PR title followed by `(#N)`. Never merge red CI.

This is the same review loop as the
[web contribution guide](https://github.com/postgrip-io/postgrip-web/blob/main/docs/development/contributing.md).
SDK checks and boundaries are owned here; web-only build commands and runner
rules do not apply to this repository. Compare these two guides whenever the
shared review process changes.

## Documentation ownership

[The documentation index](../index.md) assigns each current topic one owner.
Link to that owner instead of copying its rules into README, AGENTS, CLAUDE,
language introductions or historical records. Validate behavioral statements
against the implementation, including linked current guides; link checks alone
cannot establish semantic agreement.

Current guides describe current requirements, rationale and open gaps. Put
historical decisions, rollout chronology and past validation in separate records,
linked under **Historical decisions**. A past pass is not a current guarantee;
retain applicable rollback requirements and unresolved release gates in their
current owner. Generated reference bundles retain their immutable URLs.
