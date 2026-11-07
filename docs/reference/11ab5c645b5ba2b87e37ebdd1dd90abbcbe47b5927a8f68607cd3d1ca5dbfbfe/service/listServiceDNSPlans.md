# List canonical DNS plan history

`GET /api/v1/services/project/{serviceId}/environments/{environmentId}/domains/{domainId}/dns/plans` · `listServiceDNSPlans` · Service

> Contract bundle `11ab5c645b5ba2b87e37ebdd1dd90abbcbe47b5927a8f68607cd3d1ca5dbfbfe`
> Service contract `d8b9e8339ba1f2e4c663bfa41dcc11062c53339c9235cec6e5288d915f072377`

Lists immutable derived DNS plans and their propagation, verification, rollback, or intervention state.

## Operation

| Field | Value |
| --- | --- |
| Plane | `service` |
| Resource tags | `Administration` |
| Operation class | `tenant-api` |
| Safety | `read-only` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["services:config:read"]]` |
| Idempotency | `none` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `serviceId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `environmentId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `domainId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Successful response | `application/json` | `ServiceDNSPlanList` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "items": [
    {
      "createdAt": "2026-01-01T00:00:00Z",
      "currentObservation": {
        "observedAt": "2026-01-01T00:00:00Z",
        "records": [
          {
            "hostname": "string",
            "ttlSeconds": 1,
            "type": "A",
            "value": "string"
          }
        ]
      },
      "desiredRecords": [
        {
          "hostname": "app.example.com",
          "ttlSeconds": 60,
          "type": "CNAME",
          "value": "worker.example.com"
        },
        {
          "hostname": "_postgrip.app.example.com",
          "ttlSeconds": 60,
          "type": "TXT",
          "value": "postgrip-domain=11111111-1111-4111-8111-111111111111;proof=0123456789abcdef0123456789abcdef"
        }
      ],
      "domainId": "11111111-1111-4111-8111-111111111111",
      "expectedCanonicalGeneration": 1,
      "expectedDomainConfigurationVersion": 1,
      "id": "11111111-1111-4111-8111-111111111111",
      "kind": "activate",
      "previousRecords": [
        {
          "hostname": "string",
          "ttlSeconds": 30,
          "type": "A",
          "value": "string"
        }
      ],
      "propagationSuccesses": 1,
      "providerMode": "external",
      "reason": "string",
      "state": "planned",
      "target": {
        "deploymentId": "11111111-1111-4111-8111-111111111111",
        "environmentId": "11111111-1111-4111-8111-111111111111",
        "projectId": "11111111-1111-4111-8111-111111111111",
        "verificationUrl": "https://worker.example.com/deploy/project/environment/",
        "workerId": "11111111-1111-4111-8111-111111111111",
        "workerOrigin": "https://worker.example.com"
      },
      "updatedAt": "2026-01-01T00:00:00Z"
    }
  ]
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Lists the bounded plan history for one saved canonical domain, newest first, without exposing DNS-provider credentials.

- Use each plan state and generation to decide whether the external agent should apply, observe, roll back, or stop.

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
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  GET \
  "${POSTGRIP_API_URL}/api/v1/services/project/${POSTGRIP_SERVICE_ID}/environments/${POSTGRIP_ENVIRONMENT_ID}/domains/${POSTGRIP_DOMAIN_ID}/dns/plans" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/project/" + url.PathEscape(os.Getenv("POSTGRIP_SERVICE_ID")) + "/environments/" + url.PathEscape(os.Getenv("POSTGRIP_ENVIRONMENT_ID")) + "/domains/" + url.PathEscape(os.Getenv("POSTGRIP_DOMAIN_ID")) + "/dns/plans")
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
const url = new URL(baseUrl + "/api/v1/services/project/" + encodeURIComponent(process.env.POSTGRIP_SERVICE_ID ?? "") + "/environments/" + encodeURIComponent(process.env.POSTGRIP_ENVIRONMENT_ID ?? "") + "/domains/" + encodeURIComponent(process.env.POSTGRIP_DOMAIN_ID ?? "") + "/dns/plans");

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/project/' + urllib.parse.quote(os.environ['POSTGRIP_SERVICE_ID'], safe='') + '/environments/' + urllib.parse.quote(os.environ['POSTGRIP_ENVIRONMENT_ID'], safe='') + '/domains/' + urllib.parse.quote(os.environ['POSTGRIP_DOMAIN_ID'], safe='') + '/dns/plans'
request = urllib.request.Request(endpoint, method='GET')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)
```

## Related operations

- [adoptGitHubRepository](./adoptGitHubRepository.md) — Adopt GitHub Repository
- [applyPostGripConfigurationPlan](./applyPostGripConfigurationPlan.md) — Apply PostGrip Configuration Plan
- [applyServiceVariables](./applyServiceVariables.md) — Apply Service Variables
- [attachTargetService](./attachTargetService.md) — Attach Target Service
- [bindServiceVolume](./bindServiceVolume.md) — Bind Service Volume
- [clearServiceRepositoryCredential](./clearServiceRepositoryCredential.md) — Clear Service Repository Credential
- [clearServiceVariableValue](./clearServiceVariableValue.md) — Clear Service Variable Value
- [clearTargetServiceConnection](./clearTargetServiceConnection.md) — Clear Target Service Connection

[Back to Service index](./README.md)
