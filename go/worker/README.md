# PostGrip Worker Go client

Package `worker` is the typed client for PostGrip's public Worker management
API. It accepts the same tenant `pgt_` token used by Agent and Service clients;
endpoint scopes still determine which calls that token may make.

```sh
go get github.com/postgrip-io/postgrip-agent-sdks/go@latest
```

```go
client, err := worker.New(worker.Config{BaseURL: baseURL, Token: token})
worker, err := client.Get(ctx, workerID)
```

`worker.NewFromEnv(worker.Config{})` reads `POSTGRIP_WORKER_URL` and
`POSTGRIP_TOKEN`. The root `postgrip.Client` constructs this client together
with Agent and Service clients from one token.
