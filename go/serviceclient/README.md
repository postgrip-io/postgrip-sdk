# PostGrip Service Go client

`serviceclient` is the typed client for PostGrip's public Service API. It uses
a tenant-scoped `pgwm_` management token carrying `services:*` scopes and does
not receive worker, repository, environment, or connection credentials.

```sh
go get github.com/postgrip-io/postgrip-agent-sdks/go/serviceclient@latest
```

```go
import "github.com/postgrip-io/postgrip-agent-sdks/go/serviceclient"

client, err := serviceclient.New(serviceclient.Config{BaseURL: baseURL, Token: token})
service, err := client.Resolve(ctx, "project:6dd0d11e-87a4-4d51-8655-3cbf7cbc90a1")
selected, err := client.ForService(serviceclient.ReferenceFor(service))
status, err := selected.Status(ctx, serviceclient.OpenAPIGetServiceStatusQuery{})
```

Mutations require an explicit idempotency key. Deployments should first call
`PreviewDeploy`, present the immutable commit for confirmation, and pass the
previewed commit to `Deploy`.

The client also exposes cursor pagers, exact environment/deployment lookup,
cancellable log following, target/project checks, redeploy/cancel/rollback,
and expected-deployment-fenced start/stop/restart. It never exposes shell,
container, repository-secret, or environment-secret operations.
