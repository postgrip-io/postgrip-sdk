# Repository Guidelines

## Project Structure

This monorepo contains one SDK artifact per language. `go/`, `typescript/`, and
`python/` each expose Agent, Worker management, and Service management below
language-local `agent`, `worker`, and `service` namespaces. The Agent runtime
wire contract lives at `go/protocol/` and is mirrored into TypeScript and
Python. Tests remain inside each language package using its native layout.

The GitHub repository is `postgrip-io/postgrip-sdks`. The three release
artifacts are the Go module `github.com/postgrip-io/postgrip-agent-sdks/go`,
the npm package `@postgrip/sdk`, and the PyPI package `postgrip`. Do not add a
fourth publishable manifest or a plane-specific release path.

## Development Commands

- `cd go && go test ./...` runs the unified Go module.
- `cd go && GOWORK=off go test ./...` verifies the Go module independently.
- `cd go && go vet ./...` performs Go static analysis.
- `gofmt -w go` formats Go sources.
- `cd typescript && bun install --frozen-lockfile && bun run typecheck && bun run build && bun run test` validates TypeScript.
- `cd python && python -m pip wheel --no-deps . -w /tmp/wheel && PYTHONPATH=src python -m unittest discover -s test` validates Python.
- `python3 go/protocol/tools/check_drift.py --self-test && python3 go/protocol/tools/check_drift.py --monorepo` verifies the cross-language runtime contract.
- `python3 scripts/generate_openapi.py --plane all --check` verifies generated clients and operation metadata.
- `python3 scripts/generate_api_docs.py --check && python3 scripts/check_operation_coverage.py` verifies reference docs and endpoint ownership.
- `python3 scripts/test_api_endpoints.py --plane all --mode recorded && python3 scripts/test_curl_examples.py --plane all --mode recorded` executes every SDK operation and eligible cURL example.
- `python3 scripts/check_release_artifacts.py --ecosystem all` builds and inspects the three publishable artifacts.

## Style and Testing

Follow native conventions: `gofmt` and idiomatic exported comments for Go, two-space indentation and explicit public exports for TypeScript, and four-space PEP 8 formatting for Python. Name tests `TestBehavior` in Go, `*.test.ts` in TypeScript, and `test_*.py` in Python. Add regression coverage in every affected SDK when behavior is intended to match across languages.

## Wire Contract Changes

Treat JSON names, optionality, timestamp formats, and signing bytes as public
API. Agent HTTP models are owned by `postgrip-api/agent-openapi.json`, Worker
HTTP models by `postgrip-api/worker-openapi.json`, and Service HTTP models by
`postgrip-api/service-openapi.json`. Mirror them byte-for-byte under
`contracts/`. Regenerate the affected plane in every language and link the
coordinated server and SDK pull requests. Runtime-only models remain
protocol-owned and must update the TypeScript/Python mirrors atomically. The
Go Agent SDK must alias protocol types rather than redeclare them. Do not alter
the `agent-task-v1` signing format without adding a version.

After synchronizing a contract, run `python3 scripts/generate_openapi.py
--plane agent`, `--plane worker`, or `--plane service`; CI runs `--plane all
--check`. Never hand-edit generated operation, client, or wire-type files. Keep
schemas closed and complete. Authentication, signing, retries, cursor
following, long polling, archive streaming, and WebSocket framing stay in
transport adapters.

## Commits and Pull Requests

Use concise Conventional Commit subjects such as `feat: add sandbox sessions`,
`fix: preserve request context`, or `docs: clarify releases`. Keep commits
scoped to one coherent cross-language change. PRs should identify affected
packages, explain compatibility, link issues, and report the relevant tests
plus the monorepo drift check. All three artifacts use the root `VERSION` and
the ecosystem-prefixed tags documented in [MIGRATION.md](MIGRATION.md).
