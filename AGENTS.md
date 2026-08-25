# Repository Guidelines

## Project Structure

This monorepo contains independently released Agent, Worker management, and Service management SDKs. `protocol/` is the Go Agent runtime wire-contract source of truth. `go/`, `typescript/`, and `python/` contain Agent SDKs. Go management clients are `go/workerclient` and `go/serviceclient`; `typescript-worker/`, `typescript-service/`, `python-worker/`, and `python-service/` are the separate management artifacts. Tests remain inside each package using its native layout.

The GitHub repository is `postgrip-io/postgrip-sdks`. Published Go module
paths intentionally retain `github.com/postgrip-io/postgrip-agent-sdks/...`
for compatibility; do not rename those modules or existing Agent/Worker
directories while adding a new API plane.

## Development Commands

- `go test ./protocol/... ./go/...` runs both Go modules through the root workspace.
- `go vet ./protocol/... ./go/...` performs Go static analysis.
- `gofmt -w protocol go` formats Go sources.
- `cd typescript && bun install --frozen-lockfile && bun run typecheck && bun run build && bun run test` validates TypeScript.
- `cd python && python -m pip wheel --no-deps . -w /tmp/wheel && PYTHONPATH=src python -m unittest discover -s test` validates Python.
- `cd typescript-worker && bun install --frozen-lockfile && bun run typecheck && bun run build && bun run test` validates the TypeScript Worker SDK.
- `cd python-worker && python -m pip wheel --no-deps . -w /tmp/wheel && PYTHONPATH=src python -m unittest discover -s test` validates the Python Worker SDK.
- `cd typescript-service && bun install --frozen-lockfile && bun run typecheck && bun run build && bun run test` validates the TypeScript Service SDK.
- `cd python-service && python -m pip wheel --no-deps . -w /tmp/wheel && PYTHONPATH=src python -m unittest discover -s test` validates the Python Service SDK.
- `python3 protocol/tools/check_drift.py --self-test && python3 protocol/tools/check_drift.py --monorepo` verifies the cross-language contract.

## Style and Testing

Follow native conventions: `gofmt` and idiomatic exported comments for Go, two-space indentation and explicit public exports for TypeScript, and four-space PEP 8 formatting for Python. Name tests `TestBehavior` in Go, `*.test.ts` in TypeScript, and `test_*.py` in Python. Add regression coverage in every affected SDK when behavior is intended to match across languages.

## Wire Contract Changes

Treat JSON names, optionality, timestamp formats, and signing bytes as public API. Agent HTTP models are owned by `postgrip-api/agent-openapi.json` and mirrored as `openapi.json`. Worker HTTP models are owned by `postgrip-api/worker-openapi.json` and mirrored byte-for-byte as `worker-openapi.json`. Service HTTP models are owned by `postgrip-api/service-openapi.json` and mirrored byte-for-byte as `service-openapi.json`. Regenerate the affected plane in every language and link the coordinated server and SDK pull requests. Runtime-only models remain protocol-owned and must update the TypeScript/Python mirrors atomically. The Go Agent SDK must alias protocol types rather than redeclare them. Do not alter the `agent-task-v1` signing format without adding a version.

After synchronizing a contract, run `python3 scripts/generate_openapi.py --plane agent`, `--plane worker`, or `--plane service`; CI runs all three with `--check`. Never hand-edit generated operation, client, or wire-type files. Keep schemas closed and complete. Authentication, signing, retries, cursor following, long polling, archive streaming, and WebSocket framing stay in transport adapters.

## Commits and Pull Requests

Use concise Conventional Commit subjects such as `feat: add sandbox sessions`, `fix: preserve request context`, or `docs: clarify releases`. Keep commits scoped to one coherent cross-language change. PRs should identify affected packages, explain compatibility, link issues, and report the relevant tests plus the monorepo drift check. Package releases remain independent; use the package-prefixed tags documented in [MIGRATION.md](MIGRATION.md).
