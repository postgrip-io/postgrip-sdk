# Check Worker Orchestrator health

`GET /health` · `workerOrchestratorHealth` · Worker

> Contract bundle `b728fee5bceb4d246fe7ce81c1583d228d4f16d8f530179950fd5dccb2954820`
> Worker contract `f3ad25a26be9c31614261f7c950b1c84513033ad38d672a574590078adabcab9`

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



response, err := http.DefaultClient.Do(request)
```

### TypeScript

```ts
const baseUrl = process.env.POSTGRIP_WORKER_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/health");

const response = await fetch(url, {
  method: "GET",
  headers: {    }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_WORKER_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/health'
request = urllib.request.Request(endpoint, method='GET')



with urllib.request.urlopen(request) as response:
    result = json.load(response)
```

## Related operations

- No operation shares this resource tag.

[Back to Worker index](./README.md)
