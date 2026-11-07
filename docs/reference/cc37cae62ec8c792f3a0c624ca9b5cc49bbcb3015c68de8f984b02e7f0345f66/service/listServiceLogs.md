# List build or runtime logs

`GET /api/v1/services/{source}/{serviceId}/logs` · `listServiceLogs` · Service

> Contract bundle `cc37cae62ec8c792f3a0c624ca9b5cc49bbcb3015c68de8f984b02e7f0345f66`
> Service contract `1a03ed98a794cbce8a45d413e51db982d7b72dc1b4dcaf71452b553fbea9b16a`

Reads one page of a project service's build or runtime log. A connected service (`source` `target`) has no logs: `409` `SERVICE_OPERATION_NOT_SUPPORTED`.

## Operation

| Field | Value |
| --- | --- |
| Plane | `service` |
| Resource tags | `Logs` |
| Operation class | `tenant-api` |
| Safety | `read-only` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["services:logs:read"]]` |
| Idempotency | `none` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `source` | path | yes | `ServiceSource` | `"target"` | — |
| `serviceId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `kind` | query | no | `string` | `"build"` | — |
| `environment` | query | no | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `deployment` | query | no | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `limit` | query | no | `integer` | `1` | Page size. A missing, non-numeric, zero or negative value means 100, and a value above 200 means 200; neither is refused. |
| `cursor` | query | no | `string` | `"string"` | — |
| `follow` | query | no | `boolean` | `true` | Marks the read as one page of a follow. There is no long poll: the page is answered at once. Send `nextCursor` back after `pollAfterMs` to read the lines that arrived since. On runtime logs, `true` is refused with `409` `WORKER_UPGRADE_REQUIRED` when an environment's Worker cannot continue from a cursor. |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Logs | `application/json` | `LogList` |
| `400` | Invalid request. `INVALID_FILTER`: `kind` is not `build` or `runtime`, `environment` or `deployment` is not an id, or `follow` is not `true` or `false` (`message` says which). `INVALID_CURSOR`: the cursor is not one PostGrip issued, or was issued for another request (other filters, kind or deployment). | `application/json` | `ErrorResponse` |
| `404` | Not found. `SERVICE_NOT_FOUND`: no such service; for a build log, no deployment matches the read yet (`message` `no deployment matches this build log read yet`), for example before the app's first deployment; for a runtime log, no environment (or not the one named) has a Worker and a deployment that ran on it. | `application/json` | `ErrorResponse` |
| `409` | Conflict. `SERVICE_OPERATION_NOT_SUPPORTED`: a connected service (`source` `target`) has no logs. `WORKER_UPGRADE_REQUIRED`: an environment's Worker cannot continue a runtime log from a cursor (with `follow=true` or a `cursor`). `SERVICE_ENVIRONMENT_REQUIRED`: the read matches too many environments; name one. | `application/json` | `ErrorResponse` |
| `410` | Gone. `CURSOR_EXPIRED`: the cursor is more than 24 hours old. `CURSOR_GAP`: the lines the cursor points to were removed, the build log changed, or the environments' Worker assignment changed. Read again without `cursor`. | `application/json` | `ErrorResponse` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "items": [
    {
      "kind": "build",
      "message": "string"
    }
  ],
  "nextCursor": "string",
  "pollAfterMs": 1
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Uses the contract-defined GET /api/v1/services/{source}/{serviceId}/logs behavior.

- No additional lifecycle constraint is recorded.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_SOURCE:?set POSTGRIP_SOURCE to a percent-encoded path value}"
: "${POSTGRIP_SERVICE_ID:?set POSTGRIP_SERVICE_ID to a percent-encoded path value}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  GET \
  "${POSTGRIP_API_URL}/api/v1/services/${POSTGRIP_SOURCE}/${POSTGRIP_SERVICE_ID}/logs" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/" + url.PathEscape(os.Getenv("POSTGRIP_SOURCE")) + "/" + url.PathEscape(os.Getenv("POSTGRIP_SERVICE_ID")) + "/logs")
if err != nil { return err }
var body io.Reader
request, err := http.NewRequestWithContext(ctx, "GET", endpoint.String(), body)
if err != nil { return err }
request.Header.Set("Authorization", "Bearer "+os.Getenv("POSTGRIP_TOKEN"))


client := &http.Client{
    CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
}
response, err := client.Do(request)
```

### TypeScript

```ts
const baseUrl = process.env.POSTGRIP_SERVICE_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/api/v1/services/" + encodeURIComponent(process.env.POSTGRIP_SOURCE ?? "") + "/" + encodeURIComponent(process.env.POSTGRIP_SERVICE_ID ?? "") + "/logs");

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/' + urllib.parse.quote(os.environ['POSTGRIP_SOURCE'], safe='') + '/' + urllib.parse.quote(os.environ['POSTGRIP_SERVICE_ID'], safe='') + '/logs'
request = urllib.request.Request(endpoint, method='GET')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)
```

## Related operations

- No operation shares this resource tag.

[Back to Service index](./README.md)
