# Unified PostGrip SDK Design

Status: Proposed

Related: [Implementation plan](unified-sdk-implementation-plan.md)

## Decision summary

PostGrip will publish one SDK distribution per language ecosystem. Each
distribution exposes Agent, Worker, and Service as separate namespaces behind
one root client.

| Ecosystem | Distribution | Direct plane modules |
| --- | --- | --- |
| Go | `github.com/postgrip-io/postgrip-agent-sdks/go` | `agent`, `worker`, `service` |
| npm | `@postgrip/sdk` | `@postgrip/sdk/agent`, `/worker`, `/service` |
| PyPI | `postgrip` | `postgrip.agent`, `.worker`, `.service` |

All three distributions use the same SemVer and contract-bundle digest. A
release contains all three API planes.

An application developer supplies one tenant-bound `POSTGRIP_TOKEN`. The same
token authenticates Agent, Worker, and Service management operations according
to its endpoint scopes.

Delegated Agent runtime operations remain a separate trust class. A PostGrip
host injects short-lived session and signing credentials into a managed runtime,
and the SDK refreshes them automatically. They are not a second credential that
an application developer creates or configures.

## Context

The repository currently publishes a separate artifact for every API-plane and
language combination. Applications that use Agent tasks, Worker inventory, and
Services must discover, install, configure, and upgrade multiple packages.
Package metadata, publishing workflows, tags, and common transport behavior are
also repeated.

PostGrip is presented as one platform. Its SDK should be installed and
configured as one platform while preserving explicit domain and security
boundaries between its API planes.

## Goals

- Publish one Go module, one npm package, and one PyPI distribution.
- Expose explicit Agent, Worker, and Service namespaces.
- Use one developer-configured management token across all three planes.
- Retain least privilege through endpoint-level scopes.
- Keep Agent runtime sessions and signing isolated and automatic.
- Make HTTP and cURL first-class interfaces for AI agents and other tools.
- Publish a detailed, immutable reference page for every public operation.
- Generate language clients, documentation, cURL examples, and operation
  inventory from the same contracts.
- Account for every public operation in recorded and live test policy.
- Centralize shared transport without merging domain models or API behavior.

## Non-goals

- One undifferentiated method namespace.
- Allowing a tenant token to perform global administration.
- Sending a long-lived management token to delegated Agent runtime routes.
- Combining the three public OpenAPI contracts into one file.
- Making planes call one another implicitly.
- Preserving the existing independent package layout or release cadence.
- Shipping a CLI or MCP server in the first unified release.

## Normative decisions

### Distribution and versioning

There are exactly three public release artifacts: Go, npm, and PyPI. Agent,
Worker, and Service share one version within an artifact, and the three
ecosystems release the same version together from a root `VERSION` file.

The names in the decision table are the intended names. The official
[npm metadata endpoint](https://registry.npmjs.org/%40postgrip%2Fsdk) and
[PyPI metadata endpoint](https://pypi.org/pypi/postgrip/json) returned
`404 Not Found` for `@postgrip/sdk` and `postgrip` on 2026-08-25. The
organization must reserve both names before implementation because an
unregistered response is not a reservation. If a name cannot be claimed, only
the distribution name changes, not the architecture or public namespace model.

The SemVer impact of a release is the highest impact among all included planes.
A breaking change in Service therefore requires a major release of all three
distributions.

### Namespace convention

Direct package, module, and import names are singular: `agent`, `worker`, and
`service`. Root facade properties are:

```text
agent     # Agent plane and workflow/runtime facilities
workers   # Worker management collection
services  # Service management collection
```

The Agent runtime worker is always nested below Agent, such as
`postgrip.agent.worker` or `go/agent/worker`. The top-level `worker` module is
reserved for Worker management.

### Application and runtime modes

The SDK supports two explicit process modes.

**Application mode** uses `POSTGRIP_TOKEN` and the root facade. It can call
tenant API operations in Agent, Worker, and Service. This is the
one-token experience promised to SDK users.

**Managed runtime mode** is launched by a PostGrip host. The host injects:

```text
POSTGRIP_AGENT_ID
POSTGRIP_AGENT_ACCESS_TOKEN
POSTGRIP_AGENT_REFRESH_TOKEN
POSTGRIP_AGENT_ACCESS_EXPIRES_AT
POSTGRIP_AGENT_SIGNING_PRIVATE_KEY
```

The Agent runtime namespace loads these values and refreshes the session. The
first unified release supports host injection only; it does not exchange
`POSTGRIP_TOKEN` for an Agent session. A local process without host-injected
credentials cannot invoke delegated runtime routes.

A managed runtime may also receive `POSTGRIP_TOKEN` if its application code
needs management APIs. That remains one developer-managed token plus
host-managed runtime credentials with different authority.

### Operation classes

Every route has exactly one generated operation class and a generated set of
accepted credential types:

| Class | Accepted credential | Public SDK behavior |
| --- | --- | --- |
| `public` | None | Root or plane client where useful |
| `tenant-api` | `POSTGRIP_TOKEN`; explicitly marked Agent operations may also accept a delegated session | Root and plane clients; cURL uses the management token |
| `agent-runtime` | Delegated session and optional task signing | Agent runtime namespace and protocol tests |
| `global-admin` | Service-operator credential | Not part of public SDK contracts |

The dual credential option on selected Agent operations preserves managed
runtime behavior such as namespace visibility and workflow/task scheduling.
When called with `POSTGRIP_TOKEN`, management scopes and tenant grants apply.
When called with a delegated session, the server derives the Agent identity and
enforces its namespace, queue, lease, and capability claims. The SDK never
silently substitutes one credential class for the other.

Global-administration routes move out of the public Agent contract into an
internal server-administration contract and toolchain. They are not generated,
documented, or counted as operations in the three public SDK distributions.

### Common management token

The three public contracts use one bearer security scheme named
`postgripToken` for tenant API operations. Token format and prefix are
opaque to SDKs. The server owns issuance, expiry, tenant binding, revocation,
and scope evaluation.

Server-issued token values use URL-safe printable ASCII and exclude whitespace,
quotes, backslashes, and control characters. SDKs do not infer authority from
that syntax, but the restricted alphabet makes header construction and secure
cURL configuration unambiguous.

A token may contain grants from multiple planes. Initial scope families are:

```text
agent:read
agent:logs:read
agent:operate

workers:read
workers:logs:read
workers:operate

services:read
services:logs:read
services:operate
services:admin
services:config:read
services:config:write
services:secrets:write
```

Agent reads and exact lookups require `agent:read`; task-event and output reads
require `agent:logs:read`; enqueue, workflow, schedule, signal, update, cancel,
and sandbox mutations require `agent:operate`. Delegated Agent runtime routes
do not accept management scopes.

Broad issuance presets such as `agent:*`, `workers:*`, and `services:*` may
expand to concrete grants, but authorization evaluates the concrete scope
declared by each operation. Tenant identity comes only from the credential and
cannot be overridden by request data.

Applications that genuinely use all three planes may issue one combined token.
Separate processes or trust domains should issue different token instances
with narrower grants even though each root client accepts only one token.

### Server-contract prerequisite

The combined SDK is gated on a coordinated server release. Before publication,
the canonical public contracts and server must provide:

- the common `postgripToken` scheme;
- the Agent endpoint scope matrix;
- generated operation classes, accepted credential sets, and safety metadata;
- one error envelope containing `code`, `message`, `requestId`, and optional
  structured `details`;
- stable authentication-versus-authorization error codes;
- documented idempotency, ETag, preview, retry, timeout, pagination, streaming,
  and WebSocket behavior;
- deployed OpenAPI documents for the exact running server;
- global-administration separation from public contracts.

This standardizes cross-cutting HTTP behavior, not every domain field. Existing
plane-specific request names, response names, pagination styles, and domain
models remain contract-owned and generated unless separately redesigned.

Packaging alone cannot make one current token valid across all planes.

### Protocol ownership

The Go runtime protocol moves to `go/protocol` inside the unified Go module. It
remains the wire-contract and `agent-task-v1` signing source of truth, but no
longer has an independent version or release.

Before the move, maintainers must inventory every current protocol consumer,
including the orchestrator verifier and host Agent runtime, and update them to
the unified module path. The server and SDK changes are a coordinated cutover.
Wire bytes, JSON names, signing headers, and signing canonicalization do not
change as part of packaging consolidation.

The old protocol release stops only after every known consumer builds and its
wire/signing regression suite passes against `go/protocol`.

### Dependency policy

One distribution may contain dependencies needed by only one plane, but unused
planes must not initialize or enter the runtime dependency graph on import.

- Go compiles only imported packages; the shared module may declare Agent-only
  dependencies.
- npm subpath exports prevent importing one plane from evaluating another.
  The package retains the WebSocket dependency required by Agent sandbox
  sessions.
- Python retains `cryptography` as a base dependency for Agent signing.
  Interactive WebSocket support remains the optional `sandbox` extra, and
  management-only imports do not import that optional module.

Release CI records artifact size, installed dependency changes, build time, and
smoke-test time. Material growth requires explicit release review.

## Target architecture

```text
contracts/
  agent-openapi.json
  worker-openapi.json
  service-openapi.json

go/
  go.mod
  client.go
  agent/
  worker/
  service/
  protocol/
  internal/

typescript/
  package.json
  src/
    client.ts
    agent/
    worker/
    service/
    internal/

python/
  pyproject.toml
  src/postgrip/
    client.py
    agent/
    worker/
    service/
    _internal/
```

The root facade owns configuration resolution and constructed plane clients.
It does not duplicate generated operations, models, or routes. Plane clients
remain directly importable and do not import the root facade.

Language-internal shared transport may own URL validation, HTTP execution,
safe redirects, bounded response reads, retries, cancellation, pagination
primitives, content-type validation, and structured error decoding.
Plane-specific limits, routes, field names, auth class, and domain models
remain with their plane.

## Public client model

### Python

```sh
export POSTGRIP_URL="https://api.postgrip.io"
export POSTGRIP_TOKEN="pgt_..."
```

```python
from postgrip import PostGrip

postgrip = PostGrip.from_env()

task = postgrip.agent.tasks.create(...)
workers = postgrip.workers.list()
services = postgrip.services.list()
```

```python
from postgrip import AsyncPostGrip

async with AsyncPostGrip.from_env() as postgrip:
    workers = await postgrip.workers.list()
    services = await postgrip.services.list()
```

### TypeScript

```ts
import { PostGrip } from '@postgrip/sdk';

const postgrip = PostGrip.fromEnv();

const task = await postgrip.agent.tasks.create(...);
const workers = await postgrip.workers.list();
const services = await postgrip.services.list();
```

Focused type imports use singular subpaths:

```ts
import type { Worker } from '@postgrip/sdk/worker';
import type { Service } from '@postgrip/sdk/service';
```

### Go

```go
postgripClient, err := postgrip.NewFromEnv()
if err != nil {
	return err
}

workers, err := postgripClient.Workers.List(ctx, worker.ListOptions{})
services, err := postgripClient.Services.List(ctx, service.ListOptions{})
```

Direct plane packages remain available:

```go
import "github.com/postgrip-io/postgrip-agent-sdks/go/worker"
```

## Configuration

Configuration precedence is:

1. Explicit constructor option.
2. Plane-specific URL override.
3. `POSTGRIP_URL`.

| Variable | Purpose |
| --- | --- |
| `POSTGRIP_TOKEN` | One tenant-management token for all three planes |
| `POSTGRIP_URL` | Default base URL |
| `POSTGRIP_AGENT_URL` | Optional Agent URL override |
| `POSTGRIP_WORKER_URL` | Optional Worker URL override |
| `POSTGRIP_SERVICE_URL` | Optional Service URL override |

There are no plane-specific management token variables. Applications needing
credential isolation create separate root clients.

Constructors fail clearly when required configuration is missing. Tokens never
appear in errors, logs, debug representations, analytics, or cross-origin
redirects.

## HTTP, cURL, and AI-agent interface

Language clients are convenience layers over the public HTTP contracts. No
tenant API operation may exist only as SDK logic. An AI agent can
discover an operation in OpenAPI, execute it with cURL, parse a stable response,
and recover from a structured error.

### Secure cURL baseline

Generated examples use cURL 7.76 or newer and pass the bearer header through a
configuration on standard input so the expanded token is not placed in process
arguments:

```sh
curl --config - \
  --fail-with-body --silent --show-error \
  "${POSTGRIP_URL}/api/v1/workers" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

Mutation examples include explicit idempotency keys, ETags, preview tokens, or
confirmation tokens required by their contracts. Examples prohibit shell
tracing and never contain literal credentials. Test runners redact subprocess
output and do not add live bearer values to argv.

Streaming, WebSocket, archive, and signed Agent runtime operations receive
dedicated protocol documentation and runners. Their reference pages include a
cURL handshake or initial-request example only where stock cURL is reliable.

### Machine discovery

Production servers publish the exact deployed public contracts:

```text
GET /openapi/agent.json
GET /openapi/worker.json
GET /openapi/service.json
```

Each includes stable operation IDs, operation class, scopes, schemas,
idempotency, pagination, safety, and protocol metadata.

### Detailed and versioned API reference

Every public operation has a generated reference page containing:

- method, path, operation ID, purpose, side effects, and safety class;
- credential class and concrete scopes;
- all parameters, request content types, and closed body schemas;
- response statuses, schemas, examples, and stable error codes;
- pagination, polling, streaming, WebSocket, timeout, and retry behavior;
- idempotency, ETag, preview, impact, and confirmation requirements;
- secure cURL and equivalent Go, TypeScript, and Python examples;
- related lifecycle operations and exact contract links.

Generation computes one digest over the three public contracts. Documentation
is published immutably at:

```text
/reference/<contract-bundle-digest>/
```

`/reference/latest/` redirects to the newest deployed bundle. Each SDK embeds
its digest and links to the immutable reference, never unreleased `main`
documentation.

## Contract generation and operation ownership

The server-owned Agent, Worker, and Service OpenAPI documents remain separate.
This repository mirrors them under `contracts/` and generates language clients,
API reference pages, cURL examples, and an operation inventory.

The generated inventory contains only facts derivable from OpenAPI. Checked-in,
schema-validated annotations keyed by stable operation ID own behavioral notes,
fixtures, cleanup, test IDs, and justified protocol exceptions. CI rejects
unknown, duplicate, missing, or stale annotation entries.

Generated clients depend on plane contracts and shared internal transport, not
the root facade. Import-boundary tests enforce that direction.

## Verification policy

Every public operation is accounted for, but test cadence reflects risk and
cost:

- Pull requests run static coverage, native SDK tests, recorded HTTP
  conformance for every operation and language, real cURL tests for every
  eligible management operation, and recorded protocol runners.
- Nightly CI runs tenant API operations against disposable resources.
- Pre-release CI runs destructive Service operations, host-injected Agent
  runtime signing and refresh, archives, streams, and WebSockets in isolated
  environments.
- Production smoke tests use an explicit allowlist of public health and
  read-only operations only.

Global administration is tested in the server repository because it is absent
from public SDK contracts. Expected operation counts always derive from the
contracts. Exceptions remain visible and never count as cURL coverage.

The exact scripts, fixture rules, reports, and source refactor are specified in
the [implementation plan](unified-sdk-implementation-plan.md).

## Security consequences

A single token simplifies legitimate cross-plane applications but increases
blast radius when broad grants are issued. Endpoint scopes, tenant binding,
short expiry, rotation, and separate tokens across trust domains remain the
controls; package boundaries are not security boundaries.

Management tokens are server-side secrets. Browser, mobile, desktop, and other
untrusted clients require a delegated or user-facing authentication flow and
must not embed `POSTGRIP_TOKEN`.

Management credentials never authenticate delegated runtime routes. Runtime
credentials and signing material never become root-client configuration and
are never sent to management routes.

## Acceptance criteria

The design is implemented when:

- users install one artifact for their language;
- all three artifacts use the same version and contract-bundle digest;
- direct modules are singular and root facade properties follow the documented
  convention;
- `POSTGRIP_TOKEN` is the only developer-configured management credential;
- one correctly scoped token accesses Agent, Worker, and Service management;
- host-injected Agent runtime credentials refresh and sign automatically;
- global-administration operations are absent from public SDK contracts;
- public HTTP errors use the standardized structured envelope;
- every known protocol consumer uses `go/protocol` from the unified module;
- every public operation has immutable detailed documentation and recorded
  request coverage;
- every eligible management operation has a secure, executed cURL example;
- nightly and pre-release live suites pass in disposable environments;
- all gated phase reports and the final integration report pass against this
  design with zero unresolved deviations;
- exactly three SDK artifacts are independently publishable; publication occurs
  only after the coordinated server release and registry-owner gates pass.
