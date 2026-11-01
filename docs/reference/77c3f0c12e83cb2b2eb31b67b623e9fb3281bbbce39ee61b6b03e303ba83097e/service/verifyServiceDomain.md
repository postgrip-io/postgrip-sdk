# Verify public Service domain routing

`POST /api/v1/services/project/{serviceId}/environments/{environmentId}/domains/{domainId}/verify` · `verifyServiceDomain` · Service

> Contract bundle `77c3f0c12e83cb2b2eb31b67b623e9fb3281bbbce39ee61b6b03e303ba83097e`
> Service contract `ac469c153f7368128d5730e928553bfbbd4dbf157ea857fd1f880e5eb6ba7ee5`

Performs a bounded HTTPS request to the saved tenant domain only, persists deployment- and configuration-version-bound observations, and advances domain verification and route state when the target is still current.

## Operation

| Field | Value |
| --- | --- |
| Plane | `service` |
| Resource tags | `Operations` |
| Operation class | `tenant-api` |
| Safety | `mutation` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["services:operate"]]` |
| Idempotency | `required` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `serviceId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `environmentId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `domainId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `Idempotency-Key` | header | yes | `string` | `"recorded"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Completed public verification observation | `application/json` | `ServiceDomainVerification` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "deploymentId": "11111111-1111-4111-8111-111111111111",
  "dns": {
    "status": "passed"
  },
  "domainConfigurationVersion": 1,
  "domainId": "11111111-1111-4111-8111-111111111111",
  "environmentId": "11111111-1111-4111-8111-111111111111",
  "http": {
    "redirectCount": 1,
    "status": "passed"
  },
  "id": "11111111-1111-4111-8111-111111111111",
  "observedAt": "2026-01-01T00:00:00Z",
  "outcome": "verified",
  "projectId": "11111111-1111-4111-8111-111111111111",
  "route": {
    "status": "passed"
  },
  "tls": {
    "status": "passed"
  },
  "totalDurationMs": 1,
  "url": "https://app.example.com/"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Runs one bounded HTTPS verification against the saved tenant domain only and returns separate DNS, TLS, route, and HTTP observations.

- Idempotency: required.
- The control plane rejects private resolution, rebinding, cross-destination redirects, oversized responses, and stale deployment or configuration races.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_SERVICE_ID:?set POSTGRIP_SERVICE_ID to a percent-encoded path value}"
: "${POSTGRIP_ENVIRONMENT_ID:?set POSTGRIP_ENVIRONMENT_ID to a percent-encoded path value}"
: "${POSTGRIP_DOMAIN_ID:?set POSTGRIP_DOMAIN_ID to a percent-encoded path value}"
: "${POSTGRIP_IDEMPOTENCY_KEY:?set POSTGRIP_IDEMPOTENCY_KEY for this request}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  POST \
  --header \
  "Idempotency-Key: ${POSTGRIP_IDEMPOTENCY_KEY}" \
  "${POSTGRIP_API_URL}/api/v1/services/project/${POSTGRIP_SERVICE_ID}/environments/${POSTGRIP_ENVIRONMENT_ID}/domains/${POSTGRIP_DOMAIN_ID}/verify" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/project/" + url.PathEscape(os.Getenv("POSTGRIP_SERVICE_ID")) + "/environments/" + url.PathEscape(os.Getenv("POSTGRIP_ENVIRONMENT_ID")) + "/domains/" + url.PathEscape(os.Getenv("POSTGRIP_DOMAIN_ID")) + "/verify")
if err != nil { return err }
var body io.Reader
request, err := http.NewRequestWithContext(ctx, "POST", endpoint.String(), body)
if err != nil { return err }
request.Header.Set("Authorization", "Bearer "+os.Getenv("POSTGRIP_TOKEN"))

request.Header.Set("Idempotency-Key", os.Getenv("POSTGRIP_IDEMPOTENCY_KEY"))
client := &http.Client{
    CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
}
response, err := client.Do(request)
```

### TypeScript

```ts
const baseUrl = process.env.POSTGRIP_SERVICE_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/api/v1/services/project/" + encodeURIComponent(process.env.POSTGRIP_SERVICE_ID ?? "") + "/environments/" + encodeURIComponent(process.env.POSTGRIP_ENVIRONMENT_ID ?? "") + "/domains/" + encodeURIComponent(process.env.POSTGRIP_DOMAIN_ID ?? "") + "/verify");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,  "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/project/' + urllib.parse.quote(os.environ['POSTGRIP_SERVICE_ID'], safe='') + '/environments/' + urllib.parse.quote(os.environ['POSTGRIP_ENVIRONMENT_ID'], safe='') + '/domains/' + urllib.parse.quote(os.environ['POSTGRIP_DOMAIN_ID'], safe='') + '/verify'
request = urllib.request.Request(endpoint, method='POST')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")

request.add_header('Idempotency-Key', os.environ["POSTGRIP_IDEMPOTENCY_KEY"])
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)
```

## Related operations

- [applyServiceDNSPlan](./applyServiceDNSPlan.md) — Start External DNS Apply
- [cancelServiceDeployment](./cancelServiceDeployment.md) — Cancel a queued service deployment
- [checkService](./checkService.md) — Probe a target or deployed service
- [createServiceDNSPlan](./createServiceDNSPlan.md) — Create DNS Plan
- [deployService](./deployService.md) — Queue a deployment for a confirmed commit
- [previewServiceDeploy](./previewServiceDeploy.md) — Resolve a deploy request to an immutable commit
- [redeployService](./redeployService.md) — Queue a deployment from an existing immutable revision
- [reportServiceDNSProviderResult](./reportServiceDNSProviderResult.md) — Report External DNS Provider Result

[Back to Service index](./README.md)
