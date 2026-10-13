# Markdown-only pull request CI

## Scope

PRs whose complete tested change consists only of `.md` files should run
documentation validation without language suites, recorded endpoint/cURL
execution or artifact builds. Mixed changes, pushes to `main` and reusable
release validation retain the full suite. This is a separate CI slice from the
MVC-ish documentation cleanup and follows the shared contribution process.

## Selection and gate

- Keep workflow triggers unconditional. A small selection job checks the PR's
  tested merge commit against its first parent. Verify both parents against
  the event's base/head SHAs before trusting the comparison. Checkout depth two
  supplies those trees without downloading the full repository history.
- Use NUL-delimited Git output with rename detection disabled so a code file
  renamed to Markdown includes the deleted non-Markdown path. Every changed
  path must end in the exact `.md` suffix; additions and deletions count too.
  Empty, missing, malformed or unavailable comparison data selects full CI.
- Reusable workflow calls default to forced full validation, even when the
  caller's event context is a PR. Normal PR events have no such input. Pushes
  always select full validation.
- Documentation always checks generated reference consistency and completeness
  and builds all three MkDocs sites in strict mode. Existing generated-reference
  scripts remain the owners of those checks. Recorded cURL execution stays in
  the full contract job.
- Retain existing job IDs. Runtime jobs depend on the selection output. An
  always-running `sdk-validation` job checks that selection/documentation
  succeeded and that every selected runtime job succeeded. Intentional skips
  are accepted only for Markdown-only PRs; failures and cancellations fail the
  gate. No branch-protection settings are changed by this implementation.

## Validation

Test selection with real temporary Git merge commits: Markdown additions,
edits, deletions, mixed changes, code-to-Markdown renames, base-only changes,
unusual filenames, non-PR events, reusable calls and invalid/missing metadata.
Test the aggregate gate against missing outputs, failed/cancelled jobs and
unexpected skips. Run the policy self-tests in CI, validate workflow syntax,
and run the documentation checks selected by the new lane.

Update the current [CI owner](../development/testing.md) in the same change.
Actual GitHub job selection still needs confirmation on a hosted PR run;
local policy fixtures and syntax checks do not claim that run occurred.
