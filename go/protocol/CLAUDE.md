# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

The wire-shape **source of truth** for the PostGrip Agent runtime. The Go
package is consumed by the runtime and Go SDK, and runtime-only shapes are
**mirrored by hand** in `../../typescript/src/agent/types.ts` and
`../../python/src/postgrip/agent/types.py`. Any wire-format change must update
all mirrors in the same monorepo commit; `tools/check_drift.py --monorepo`
enforces matching field names.

The package import path is
`github.com/postgrip-io/postgrip-agent-sdks/go/protocol`. It ships as part of
the unified Go module with `go/v*` repository tags.

**This package is not the high-level client surface.** Agent client types in
`../agent/client/aliases.go` alias protocol definitions so application code
can stay within the Agent namespace.

## Commands

```sh
go test ./...                                  # types + signing tests
go test -run TestSign -v                       # single test or pattern
go vet ./...
gofmt -l . | grep -v '^tools/'                 # CI ignores tools/ (Python lives there)

python3 tools/check_drift.py --monorepo        # check every local SDK mirror
python3 tools/check_drift.py --from-github     # check vs TS/Python main on GitHub
python3 tools/check_drift.py --self-test       # exercise the detectors themselves
```

Root CI runs formatting, vet, tests, and the local monorepo drift check
(`../../.github/workflows/ci.yml`). **A failing drift job is a real signal**,
not noise—it means the same commit contains incompatible wire definitions.

The drift job runs `--self-test` **before** the tree scan. A clean tree only proves today's type files agree; it never proves the checker still detects disagreement. The self-test caught a live bug in its own first run — the literal-const regex captured `const` as the name on single-line declarations — which is exactly the failure mode it exists to prevent.

## Architecture

### What lives in this package vs. what doesn't

`types.go` carries only structs that flow over the runtime-service wire — task envelopes, workflow execution rows, schedule shapes, agent enrollment requests, failure info, history events. SDK-side conveniences (e.g. the typed `ShellExecInput` / `WorkflowStartOptions` shapes) live in the SDK package and are **separate from** the wire types. Don't pull SDK ergonomics into protocol; don't add agent-implementation specifics here.

`signing.go` carries Ed25519 task-result signing — both the customer-side signer and the orchestrator-side verifier. It's wire-protocol concern (the canonical-request format is part of the contract) so it lives here, not in the SDK.

### The drift contract

The contract being checked is narrow: every exported Go struct that represents a wire shape has an equivalent type with matching name in `types.ts` and `types.py`, and every JSON-tagged field on that struct appears as a same-name field on the TS interface and the Python TypedDict. **Field types are not yet checked** (e.g. int vs string drift goes undetected); same for optional-vs-required. Both are tagged `# v2` in `tools/check_drift.py` and need a cross-language type table to address.

When you add, rename, or remove a field on a wire struct, update the TypeScript and Python paths in the same commit. The monorepo removes cross-repository branch and push-order races, but requiredness and field types still require human review.

### Go aliases are checked differently

The Go Agent client at `../agent/client` is not a mirror—it imports this
package and re-exports wire types as aliases, so field-set comparison does not
apply. Monorepo drift validation scans the SDK tree and fails on any struct or
string-literal constant whose name collides with something protocol owns. The
fix is to alias the protocol declaration.

This check prevents `WorkflowRuntimePayload`, `TaskTypeWorkflowRuntime`, and
other protocol-owned declarations from drifting into local copies.

### Custom `UnmarshalJSON` on `Task`

`types.go` has a hand-rolled `Task.UnmarshalJSON` that re-decodes through a private `rawTask` shadow type. Reason: certain timestamp fields the runtime emits as either RFC3339 or epoch-seconds depending on origin; the shadow lets us normalize without affecting `Task`'s public field shape. **Don't simplify back to a default unmarshal** without verifying the runtime emits canonical RFC3339 in every code path — the shadow tolerates legacy formats that older runtime versions still produce.

### Signing format invariants

`signing.go` builds a canonical request string with a domain separator (`agent-task-v1\n`) followed by `METHOD\nPATH\nQUERY\nTIMESTAMP\nBODY_SHA256_BASE64\n`. **Don't change this format without bumping the version prefix** (`agent-task-v2`, etc.) — agents and orchestrators must agree on the bytes exactly, and an unannounced format change silently breaks every signed request. The version prefix exists precisely so future formats can coexist during a rollout.

The orchestrator-side verifier rejects timestamps outside `MaxAgentSignatureSkew` (5 minutes default) of server time. Symmetric window means the longest a captured signed request can stay replayable is ~10 minutes (past + future skew). Customer agent hosts must run NTP; clock-drifted agents show up in audits as `signature timestamp outside accepted skew`.

The signature header carries a key ID (`first 16 hex chars of sha256(pubkey)`) but the orchestrator looks up the active key by **agent identity**, not by key id, today. The header is preserved for future overlapping-key rotation. Don't introduce code that authenticates on the key id alone — agent identity is the trust root.

## Polyglot mirror

This package is part of the single Go module in the `postgrip-sdks` monorepo:

- `go/protocol/` (this) — the Agent runtime wire source of truth.
- `go/agent/` — Go Agent SDK; imports this package directly.
- `typescript/` — unified TypeScript SDK; mirrors runtime types in `src/agent/types.ts`.
- `python/` — unified Python SDK; mirrors runtime types in `src/postgrip/agent/types.py`.

The runtime (`postgrip-io/postgrip-web`) also imports this package directly and is the canonical implementer of the orchestrator side. Wire-shape changes that touch `types.go` should be reviewed with both the runtime and the SDKs in mind; a wire change without runtime support is wasted work.
