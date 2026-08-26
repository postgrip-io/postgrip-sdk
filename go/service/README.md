# PostGrip Service Go client

Package `service` is the typed client for PostGrip's public Service API. It uses
a tenant-scoped `pgt_` token carrying the required Service scopes and does
not receive worker-local paths or readable repository, environment, or
connection credentials.

```sh
go get github.com/postgrip-io/postgrip-agent-sdks/go@latest
```

```go
import "github.com/postgrip-io/postgrip-agent-sdks/go/service"

client, err := service.New(service.Config{BaseURL: baseURL, Token: token})
resolved, err := client.Resolve(ctx, "project:6dd0d11e-87a4-4d51-8655-3cbf7cbc90a1")
selected, err := client.ForService(service.ReferenceFor(resolved))
status, err := selected.Status(ctx, service.OpenAPIGetServiceStatusQuery{})

volumes, err := client.ManagedVolumes().List(ctx, projectID)
impact, err := client.Projects().RemovalImpact(ctx, projectID)
```

`service.NewFromEnv(service.Config{})` reads
`POSTGRIP_SERVICE_URL` and `POSTGRIP_TOKEN`. Explicit
configuration remains authoritative. Retries are disabled by default; enabling
them permits at most three attempts, with configurable caps that cannot exceed
the contract's 2-second backoff and 30-second `Retry-After` limits.

Mutations require an explicit idempotency key. Administration mutations also
take `WriteOptions` with the current `If-Match` ETag. Deletions and worker
reassignments use a fresh impact/preview token; durable worker fan-out returns a
configuration-operation ID that can be inspected or retried through
`ServiceConfigurationOperations()`.

The grouped administration clients cover targets, projects, environments,
managed volumes, domains, variables, repository settings, promotions,
retention, and configuration operations. Credential values are write-only and
never appear in response models. Deployments should first call `PreviewDeploy`,
present the immutable commit for confirmation, and pass the previewed commit to
`Deploy`.

The client also exposes cursor pagers, exact environment/deployment lookup,
cancellable log following, target/project checks, redeploy/cancel/rollback,
and expected-deployment-fenced start/stop/restart. It never exposes shell,
container, direct database, or secret-read operations.
