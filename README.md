# PostGrip SDKs

[![CI](https://github.com/postgrip-io/postgrip-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/postgrip-io/postgrip-sdk/actions/workflows/ci.yml)
[![Go Reference](https://pkg.go.dev/badge/github.com/postgrip-io/postgrip-agent-sdks/go.svg)](https://pkg.go.dev/github.com/postgrip-io/postgrip-agent-sdks/go)
[![npm](https://img.shields.io/npm/v/%40postgrip%2Fsdk.svg?logo=npm)](https://www.npmjs.com/package/@postgrip/sdk)
[![PyPI](https://img.shields.io/pypi/v/postgrip.svg?logo=pypi)](https://pypi.org/project/postgrip/)

One PostGrip SDK per language, each supporting Agent, Worker, and Service APIs
with one tenant-bound `POSTGRIP_TOKEN`.

| Language | Install | Direct planes |
| --- | --- | --- |
| Go | `github.com/postgrip-io/postgrip-agent-sdks/go` | `/agent`, `/worker`, `/service` |
| TypeScript | `@postgrip/sdk` | `@postgrip/sdk/agent`, `/worker`, `/service` |
| Python | `postgrip` | `postgrip.agent`, `.worker`, `.service` |

All three artifacts release from [VERSION](VERSION). The Go import retains the
historical repository segment intentionally; the GitHub repository is
`postgrip-io/postgrip-sdk`.

## Install

```sh
go get github.com/postgrip-io/postgrip-agent-sdks/go@latest
npm install @postgrip/sdk
pip install postgrip
```

## Configure once

```sh
export POSTGRIP_URL="https://api.postgrip.io"
export POSTGRIP_TOKEN="pgt_..."
```

`POSTGRIP_AGENT_URL`, `POSTGRIP_WORKER_URL`, and `POSTGRIP_SERVICE_URL`
optionally override the common URL. Precedence is explicit constructor value,
plane-specific environment value, then `POSTGRIP_URL`. There are no
plane-specific management token variables.

The token must carry the concrete scopes required by the operations you call.
One token can contain Agent, Worker, and Service scopes; a token does not gain
authority merely because one root client sends it to all three planes. Host-
injected Agent runtime access, refresh, and signing credentials are a separate
trust class and are never root-client configuration.

## Use all three planes

### Go

```go
postgripClient, err := postgrip.NewFromEnv()
if err != nil { return err }

tasks, err := postgripClient.Agent.Task.List(ctx, nil)
workers, err := postgripClient.Workers.List(ctx, worker.ListWorkersOptions{})
services, err := postgripClient.Services.List(ctx, service.OpenAPIListServicesQuery{})
```

### TypeScript

```ts
import { PostGrip } from '@postgrip/sdk';

const postgrip = PostGrip.fromEnv();
const tasks = await postgrip.agent.task.list();
const workers = await postgrip.workers.list();
const services = await postgrip.services.list();
```

Focused imports do not initialize another plane:

```ts
import { WorkerClient } from '@postgrip/sdk/worker';
import type { OpenAPIWorker } from '@postgrip/sdk/worker';
```

### Python

```python
from postgrip import PostGrip

postgrip = PostGrip.from_env()
tasks = postgrip.agent.task.list()
workers = postgrip.workers.list()
services = postgrip.services.list()
```

```python
from postgrip import AsyncPostGrip

async with AsyncPostGrip.from_env() as postgrip:
    workers = await postgrip.workers.list()
    services = await postgrip.services.list()
```

## API reference and cURL

The [immutable API reference](docs/reference/README.md) contains one generated
page for every public operation: method and path, scopes, credential class,
parameters, request and response schemas, safety, retries, idempotency,
pagination, lifecycle notes, secure cURL, and equivalent language HTTP.

The generated index selects the current contract bundle; older bundles retain
their immutable URLs.
Generated cURL passes the bearer through a configuration on standard input, so
the expanded token is absent from the process argument list:

```sh
set +x
curl --config - \
  --fail-with-body --silent --show-error \
  "${POSTGRIP_URL}/api/v1/workers" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

See [authentication](docs/authentication.md), the [cURL guide](docs/curl.md),
and [configuration](docs/configuration.md).

## Repository layout

```text
contracts/    synchronized Agent, Worker, and Service OpenAPI contracts
go/           one Go module: root facade, agent, worker, service, protocol
typescript/   one npm package with root and singular subpath exports
python/       one PyPI package with root and singular modules
test/         operation ownership and behavior annotations
docs/         current guides, generated reference and historical records
scripts/      deterministic generation, drift, docs, and conformance tooling
```

Generated clients embed the same contract-bundle digest. Runtime-only wire
types and `agent-task-v1` signing remain owned by `go/protocol`; TypeScript and
Python mirrors change atomically.

## Development

Use the [contribution and review guide](docs/development/contributing.md),
[validation commands](docs/development/testing.md), and
[web coordination procedure](docs/development/contracts.md).
The [documentation index](docs/index.md) identifies each current topic owner.

## Security

Management tokens are server-side secrets. Do not embed them in browsers,
mobile apps, desktop binaries, logs, shell traces, URLs, or command arguments.
Use separate root clients and separately issued tokens when an application
requires credential isolation.

Licensed under [Apache-2.0](LICENSE).
