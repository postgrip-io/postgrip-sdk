# PostGrip Go SDK

One module exposes Agent, Worker, and Service clients:

```sh
go get github.com/postgrip-io/postgrip-agent-sdks/go@latest
```

```go
import (
    postgrip "github.com/postgrip-io/postgrip-agent-sdks/go"
    "github.com/postgrip-io/postgrip-agent-sdks/go/service"
    "github.com/postgrip-io/postgrip-agent-sdks/go/worker"
)

client, err := postgrip.NewFromEnv()
if err != nil { return err }

tasks, err := client.Agent.Task.List(ctx, nil)
workers, err := client.Workers.List(ctx, worker.ListWorkersOptions{})
services, err := client.Services.List(ctx, service.OpenAPIListServicesQuery{})
```

Configure `POSTGRIP_URL` and one `POSTGRIP_TOKEN`. Optional
`POSTGRIP_AGENT_URL`, `POSTGRIP_WORKER_URL`, and `POSTGRIP_SERVICE_URL`
override the common URL when using `NewFromEnv()`. `New(Config)` uses explicit
root configuration. See [configuration](../docs/configuration.md) for constructor
and environment behavior.

Direct packages remain available without constructing the root facade:

- `go/agent/client`, `go/agent/worker`, `go/agent/workflow`, and
  `go/agent/activity` for Agent application and managed-runtime behavior;
- `go/worker` for Worker inventory, jobs, logs, and operations;
- `go/service` for Service inventory, deployments, runtime, logs, and
  administration;
- `go/protocol` for runtime wire types and signing used by PostGrip
  infrastructure consumers.

The module path intentionally retains `postgrip-agent-sdks` for published Go
compatibility even though the repository is `postgrip-sdk`.

See the repository [quick start](../README.md), [authentication
model](../docs/authentication.md), and [generated API
reference](../docs/reference/77c3f0c12e83cb2b2eb31b67b623e9fb3281bbbce39ee61b6b03e303ba83097e/README.md).
Durable public Worker creation is covered in the [Worker bootstrap
guide](../docs/worker-bootstrap.md).

```sh
GOWORK=off go test ./...
GOWORK=off go vet ./...
```
