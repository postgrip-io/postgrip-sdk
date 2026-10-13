# SDK validation and CI

Run commands from the repository root unless shown otherwise. Start with the
narrowest affected tests; for shared behavior, validate every affected SDK.
Use Go's native tests, Vitest (`*.test.ts`), and Python unittest (`test_*.py`).

```sh
(cd go && GOWORK=off go test ./... && GOWORK=off go vet ./...)
(cd typescript && bun install --frozen-lockfile && bun run typecheck && bun run build && bun run test)
(cd python && python3 -m pip wheel --no-deps . -w /tmp/postgrip-wheel && PYTHONPATH=src python3 -m unittest discover -s test)
python3 go/protocol/tools/check_drift.py --self-test
python3 go/protocol/tools/check_drift.py --monorepo
python3 scripts/generate_openapi.py --plane all --check
python3 scripts/check_operation_inventory.py
python3 scripts/check_package_layout.py
python3 scripts/generate_api_docs.py --check
python3 scripts/check_operation_coverage.py
python3 scripts/test_api_endpoints.py --plane all
python3 scripts/test_curl_examples.py --plane all
python3 scripts/check_release_artifacts.py --ecosystem all
python3 -m unittest discover -s scripts -p test_ci_policy.py
```

The endpoint and cURL runners exercise recorded transports. They establish
request/response conformance, not successful deployment or live side effects.
The [generated coverage report](https://github.com/postgrip-io/postgrip-sdk/blob/main/test/reports/operation-coverage.md)
owns operation counts and tier assignments. [Live testing](../live-testing.md)
owns deployed evidence requirements and resource cleanup. Run its safety
self-tests without credentials; live execution needs the configured disposable
fixtures and consent described there. No silent skips may stand in for coverage.

## Documentation checks

Run `python3 scripts/generate_api_docs.py --check` and
`python3 scripts/check_api_docs.py`, then with
`mkdocs-material>=9.7,<10` installed:

```sh
mkdocs build --strict --site-dir /tmp/postgrip-docs
(cd typescript && mkdocs build --strict --site-dir /tmp/postgrip-docs-typescript)
(cd python && mkdocs build --strict --site-dir /tmp/postgrip-docs-python)
```

Check changed relative links, examples and current topic-owner agreement.
Use the [responsibility checklist](architecture.md#responsibility-review) for
semantic review. Compare AGENTS, affected guides and their linked current
references with source and workflow behavior; correct conflicts together.
Distinguish mandatory architecture from existing implementation gaps and
proposed designs. Passing documentation builds or link checks does not prove
those claims agree.
Go's Agent documentation uses Jekyll; the documentation publishing workflow
builds it separately. MkDocs does not validate that site's Liquid links.

## Executable CI owners

[ci.yml](https://github.com/postgrip-io/postgrip-sdk/blob/main/.github/workflows/ci.yml)
runs documentation validation on every PR and `main` push, and supports reusable
workflow calls. A PR whose complete tested diff contains only `.md` paths runs
the `changes` policy tests/selection, `documentation` and `sdk-validation` gate.
Documentation verifies generated API reference consistency/completeness and
builds all three MkDocs sites in strict mode. Language suites, contract/runtime
checks, recorded endpoint/cURL execution and artifact builds are skipped only
for that Markdown-only PR case.

Mixed changes, non-`.md` documentation files, empty or unverifiable diffs, and
pushes to `main` run the full suite. The selector compares the tested PR merge
with its base after verifying both parents against the event; rename detection
is disabled so both old and new paths count. Reusable calls default to
`force_full: true`, including callers triggered by PRs, preserving release
validation. The always-running `sdk-validation` gate rejects failures,
cancellations, missing selection output and unexpected skips. Existing job IDs
are retained; this change does not configure repository branch protection.

It uses GitHub-hosted `ubuntu-latest`, including Python 3.11/3.12/3.13.
[docs.yml](https://github.com/postgrip-io/postgrip-sdk/blob/main/.github/workflows/docs.yml)
selects documentation pushes and publishes the combined MkDocs/Jekyll site.

Markdown selection and its gate are implemented in `scripts/ci_policy.py` and
tested with real temporary Git merges in `scripts/test_ci_policy.py`.
Unlike
[web CI](https://github.com/postgrip-io/postgrip-web/blob/main/docs/development/ci.md),
the SDK still has tag-based action references, some unbounded jobs and CI concurrency
that cancels superseded `main` runs. These are explicit CI gaps, not documentation
claims that web's enforcement already exists here. Changing them requires a
separate workflow design and validation. Web's six light/eight heavy self-hosted
runner pool is not the runner configuration of these SDK workflows.

## Historical decisions

See the [historical SDK records](../archive/index.md) for the unification design,
phase evidence and dated simplification review. Current requirements are above;
old results do not establish present release readiness.
