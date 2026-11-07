# Liveness probe

`GET /healthz` · `health` · Agent

> Contract bundle `87c0db92da44a39eb7a85c5f5b39186dbebc8e8f243cab5e1462838c7742a017`
> Agent contract `b888f64c8796fe545f48c8ea7b04fe52dd4ac7fe544611940c65d52537ae2e1a`

Returns a fixed ok status without touching the store. It needs no credential at all, so an uptime monitor can call it. (`refreshAgentSession` is also public, but its body carries a refresh token.)

## Operation

| Field | Value |
| --- | --- |
| Plane | `agent` |
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
| `200` | Service health | `application/json` | `HealthResponse` |

Illustrative success body:

```json
{
  "status": "string"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Returns a fixed ok status without touching the store. This is the only route that bypasses authentication entirely, so an uptime monitor can call it with no credential.

- No additional lifecycle constraint is recorded.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_AGENT_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
curl \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  GET \
  "${POSTGRIP_API_URL}/healthz"
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_AGENT_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/healthz")
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
const baseUrl = process.env.POSTGRIP_AGENT_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/healthz");

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: {    }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_AGENT_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/healthz'
request = urllib.request.Request(endpoint, method='GET')



class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)
```

## Related operations

- [ready](./ready.md) — Readiness probe with store counts

[Back to Agent index](./README.md)
