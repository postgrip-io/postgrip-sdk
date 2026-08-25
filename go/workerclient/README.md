# PostGrip Worker Go client

`workerclient` is the typed client for PostGrip's public Worker management API.
It requires a dedicated `pgwm_` token and does not depend on Agent sessions.

```sh
go get github.com/postgrip-io/postgrip-agent-sdks/go/workerclient@latest
```

```go
client, err := workerclient.New(workerclient.Config{BaseURL: baseURL, Token: token})
worker, err := client.Get(ctx, workerID)
```
