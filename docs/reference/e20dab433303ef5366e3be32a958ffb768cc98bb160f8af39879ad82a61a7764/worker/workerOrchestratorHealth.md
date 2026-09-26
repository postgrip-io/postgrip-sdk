# Check Worker Orchestrator health

`GET /health` · `workerOrchestratorHealth` · Worker

> Contract bundle `e20dab433303ef5366e3be32a958ffb768cc98bb160f8af39879ad82a61a7764`
> Worker contract `ffce1b8c3053f64e6efa1740a9ae8c124cbc6f49fc0754d51e608688ed115dc7`

Uses the contract-defined GET /health behavior.

## Operation

| Field | Value |
| --- | --- |
| Plane | `worker` |
| Resource tags | `System` |
| Operation class | `public` |
| Safety | `read-only` |
| Protocol | `http-json` |
| Credentials | none |
| Required scopes | `[]` |
| Idempotency | `none` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

This operation has no path or query parameters.

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Healthy | `application/json` | `HealthResponse` |

Illustrative success body:

```json
{
  "status": "ok"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Uses the contract-defined GET /health behavior.

- No additional lifecycle constraint is recorded.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_WORKER_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
curl \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  GET \
  "${POSTGRIP_API_URL}/health"
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_WORKER_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/health")
if err != nil { return err }
var body io.Reader
request, err := http.NewRequestWithContext(ctx, "GET", endpoint.String(), body)
if err != nil { return err }



client := &http.Client{
    CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
}
response, err := client.Do(request)
```

### TypeScript

```ts
const baseUrl = process.env.POSTGRIP_WORKER_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/health");

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: {    }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_WORKER_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/health'
request = urllib.request.Request(endpoint, method='GET')



class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)
```

## Related operations

- No operation shares this resource tag.

[Back to Worker index](./README.md)
