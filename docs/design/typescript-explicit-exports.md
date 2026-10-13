# Explicit TypeScript plane exports

Date: 2026-10-13. Status: proposed.

## Problem and boundaries

[Architecture](../development/architecture.md) requires explicit named ESM
exports and deliberate package subpaths. The root entry `src/index.ts` complies,
but the SDK architecture audit of `main` at `3675b2f2` found five wildcard
re-exports in the plane entries:

- `src/worker/index.ts` and `src/service/index.ts` re-export everything from
  `./client.js` and `./generated/openapi.js`.
- `src/agent/index.ts` names its handwritten exports, but re-exports everything
  from `./generated/openapi.js`.

Any name a generator run or a client edit adds therefore becomes public without
review. No check records the published surface, so replacing the wildcards
could also drop a published name unnoticed. `scripts/check_package_layout.py`
checks package subpaths, not entry contents.

This design covers the four TypeScript package entries (`.`, `./agent`,
`./worker`, `./service`) and the checks that keep them explicit. Contracts,
generated module contents, runtime behavior, the root facade, and Python and
Go exports do not change. Follow [contracts](../development/contracts.md) and
[validation](../development/testing.md).

## Design

### Recorded public surface

`typescript/test/public-surface.json` records, for each package entry, the
sorted exported names and whether each is a value or a type only. A Vitest test,
`typescript/test/public-surface.test.ts`, uses the TypeScript compiler API that
the package already depends on. It reads each entry's exports from source and
fails on any added, removed or reclassified name, printing the difference. The
existing `bun run test` step in CI runs it, so it needs no new job.

The initial manifest is the surface published today, generated once from the
current wildcard entries. Changing it is a deliberate edit reviewed with the
code that changes the surface.

### Explicit entries

Each plane entry lists every public name explicitly:
`export { … } from` for values and `export type { … } from` for types, grouped
by source module and sorted. The lists equal today's surface exactly, so the
manifest is unchanged by the conversion. The root entry already complies.

The generator keeps writing only `generated/openapi.ts`; it does not edit
entries. When a contract change adds a schema or operation, the contributor
adds its public names to the plane entry and the manifest in the same PR. This
is the deliberate step the wildcard skipped. [Contracts](../development/contracts.md)
states this step beside the existing generation steps.

### Wildcard rule

`scripts/check_package_layout.py` rejects `export *` and `export * as` in any
module under `typescript/src`. A `--self-test` mode proves the rule against
generic in-memory fixtures: wildcard, namespace wildcard, and type-only
wildcard forms fail, while named value, named type and comment-only forms pass.
CI's contracts job runs `--self-test` before the repository check, as it does
for the drift and inventory checkers. This is the first generic fixture for
this checker. The allowed-edge matrix planned in the contract-driven layering
design (PR #69) extends the same self-test.

## Compatibility

No published name is added, removed or changed between value and type. Import
paths and runtime behavior do not change. Future contract additions become
public only when their names are added to the entry and manifest.

## Delivery slices

1. **Surface record and explicit entries.** Add the manifest and test, replace
   the five wildcards with explicit lists, and update the contracts guide's
   generation steps.
2. **Wildcard rule.** Add the `check_package_layout.py` rule with `--self-test`
   fixtures and run the self-test in CI. Update the architecture and validation
   guides' description of what the checker enforces.

Each slice is its own PR under the [review process](../development/contributing.md).

## Acceptance

- The public-surface test passes against the manifest generated from the
  wildcard entries before the conversion, and still passes after it.
- Temporarily adding, removing or reclassifying an entry name makes the test
  fail with that name.
- `bun run typecheck`, `bun run build`, `bun run test` and
  `npm pack --dry-run` pass, and the built `dist/*/index.d.ts` files contain no
  `export *`.
- `check_package_layout.py --self-test` and the repository check pass, and the
  repository check fails on a temporary wildcard in `typescript/src`.
- Generator, drift and documentation checks pass unchanged.
