# Contracts and coordination with web

The repository is `postgrip-io/postgrip-sdk`. Preserve the published Go module
path `github.com/postgrip-io/postgrip-agent-sdks/go`; a repository rename does
not authorize changing consumer imports. There is one artifact per language:
that Go module, `@postgrip/sdk`, and `postgrip` on PyPI.

## HTTP contracts

[Web's API contract guide](https://github.com/postgrip-io/postgrip-web/blob/main/docs/development/api-contracts.md)
owns server contract changes, discovery bundles and the SDK revision pinned by
web. Its `postgrip-api/{agent,worker,service}-openapi.json` files are canonical;
this repository's `contracts/` files are byte-for-byte mirrors.

For an SDK-facing route, schema, enum or wire change:

1. Update the canonical web contract with its owning service. Run web's
   `bun run api:check` and affected observable server tests.
2. Copy the affected contracts byte-for-byte into `contracts/`; never edit a
   mirror independently to describe a server behavior that does not exist.
3. Run `python3 scripts/generate_openapi.py --plane all` and
   `python3 scripts/generate_api_docs.py`. Update operation annotations and
   test ownership when the generator/checkers require them. Do not hand-edit
   generated bindings or reference pages. Keep schemas closed and complete.
4. Run the [SDK validation](testing.md) appropriate to every affected language,
   including recorded endpoint/cURL coverage and observable behavior tests.
   A generated method or tier assignment alone is not proof of live success.
5. Link coordinated PRs and record server/SDK revisions, contract digests and
   validation results. Follow web's guide when advancing its SDK source pin,
   regenerating discovery and updating workflow refs. A docs-only SDK merge
   does not require moving that pin. Follow [release gates](../releasing.md)
   before publishing changed artifacts.

`scripts/_contracts.py:digest_bundle` computes the digest from the three named
contract files and their bytes. [The reference index](../reference/README.md)
is the generated current pointer; older digest directories preserve historical
URLs. A checked-in contract describes that revision, not deployment evidence.

## Runtime protocol

`go/protocol/` owns runtime-only wire types and `agent-task-v1` signing.
TypeScript `src/agent/types.ts` and Python `src/postgrip/agent/types.py` mirror
those types atomically; Go Agent client declarations alias protocol types.
HTTP-owned models come from OpenAPI. Do not add competing local structs.

Preserve JSON names, optionality, timestamp formats and signing bytes. Run both
`check_drift.py --self-test` and `--monorepo` from the validation guide. The
checker verifies configured names/fields and Go duplicate declarations; it does
not prove type or requiredness compatibility. Review those and runtime consumers
explicitly. A signing-format change needs a versioned prefix and coordinated
runtime support, never an unannounced change to `agent-task-v1`.

Management tokens, delegated runtime sessions and public bootstrap requests
remain separate [authentication lanes](../authentication.md). Keep signing,
refresh, retry, cursor following, long polling, archives and WebSocket framing
in runtime adapters rather than generated clients. Global administration and
worker-local secret reads must not enter public contracts.
