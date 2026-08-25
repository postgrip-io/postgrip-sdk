# PostGrip Service Go client

`serviceclient` is the typed client for PostGrip's public Service API. It uses
a tenant-scoped `pgwm_` management token carrying `services:*` scopes and does
not receive worker-local paths or readable repository, environment, or
connection credentials.

```sh
go get github.com/postgrip-io/postgrip-agent-sdks/go/serviceclient@latest
```

```go
import "github.com/postgrip-io/postgrip-agent-sdks/go/serviceclient"

client, err := serviceclient.New(serviceclient.Config{BaseURL: baseURL, Token: token})
service, err := client.Resolve(ctx, "project:6dd0d11e-87a4-4d51-8655-3cbf7cbc90a1")
selected, err := client.ForService(serviceclient.ReferenceFor(service))
status, err := selected.Status(ctx, serviceclient.OpenAPIGetServiceStatusQuery{})

volumes, err := client.ManagedVolumes().List(ctx, projectID)
impact, err := client.Projects().RemovalImpact(ctx, projectID)
```

`serviceclient.NewFromEnv(serviceclient.Config{})` reads
`POSTGRIP_WORKERORCHESTRATOR_URL` and `POSTGRIP_SERVICE_API_TOKEN`. Explicit
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
