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
```

The endpoint and cURL runners exercise recorded transports. They establish
request/response conformance, not successful deployment or live side effects.
The [generated coverage report](https://github.com/postgrip-io/postgrip-sdk/blob/main/test/reports/operation-coverage.md)
owns operation counts and tier assignments. [Live testing](../live-testing.md)
owns deployed evidence requirements and resource cleanup. Run its safety
self-tests without credentials; live execution needs the configured disposable
fixtures and consent described there. No silent skips may stand in for coverage.

## Documentation checks

Run `python3 scripts/generate_api_docs.py --check`, then with
`mkdocs-material>=9.7,<10` installed:

```sh
mkdocs build --strict --site-dir /tmp/postgrip-docs
(cd typescript && mkdocs build --strict --site-dir /tmp/postgrip-docs-typescript)
(cd python && mkdocs build --strict --site-dir /tmp/postgrip-docs-python)
```

Check changed relative links, examples and current topic-owner agreement.
Go's Agent documentation uses Jekyll; the documentation publishing workflow
builds it separately. MkDocs does not validate that site's Liquid links.

## Executable CI owners

[ci.yml](https://github.com/postgrip-io/postgrip-sdk/blob/main/.github/workflows/ci.yml)
runs contracts, language suites, recorded endpoints, artifact inspection and
MkDocs on every PR and `main` push, and supports reusable workflow calls.
It uses GitHub-hosted `ubuntu-latest`, including Python 3.11/3.12/3.13.
[docs.yml](https://github.com/postgrip-io/postgrip-sdk/blob/main/.github/workflows/docs.yml)
selects documentation pushes and publishes the combined MkDocs/Jekyll site.

The SDK currently has no Markdown-only CI reduction. Unlike
[web CI](https://github.com/postgrip-io/postgrip-web/blob/main/docs/development/ci.md),
it also has tag-based action references, unbounded jobs and CI concurrency
that cancels superseded `main` runs. These are explicit CI gaps, not documentation
claims that web's enforcement already exists here. Changing them requires a
separate workflow design and validation. Web's six light/eight heavy self-hosted
runner pool is not the runner configuration of these SDK workflows.
