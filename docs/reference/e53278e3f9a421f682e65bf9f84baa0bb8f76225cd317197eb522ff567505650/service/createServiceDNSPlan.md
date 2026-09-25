# Preview an immutable provider-neutral DNS plan

`POST /api/v1/services/project/{serviceId}/environments/{environmentId}/domains/{domainId}/dns/plans` · `createServiceDNSPlan` · Service

> Contract bundle `e53278e3f9a421f682e65bf9f84baa0bb8f76225cd317197eb522ff567505650`
> Service contract `08309318d5a9624cb4447f01417077eed5c1f0d21f02bcfe8c9c6f386ccd8a30`

Derives an exact CNAME or address record plus ownership TXT proof from a tenant-owned configured hostname and current ready release. The caller cannot submit arbitrary record names, types, or targets.

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

Content type: `application/json` · Schema: `CreateServiceDNSPlanRequest`

```json
{
  "expectedCanonicalGeneration": 1,
  "expectedDomainConfigurationVersion": 1,
  "expectedTargetDeploymentId": "11111111-1111-4111-8111-111111111111",
  "kind": "activate",
  "reason": "initial_activation",
  "targetEnvironmentId": "11111111-1111-4111-8111-111111111111",
  "targetProjectId": "11111111-1111-4111-8111-111111111111",
  "ttlSeconds": 30
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `201` | Successful response | `application/json` | `ServiceDNSPlan` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
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
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Derives an exact CNAME or address record plus PostGrip ownership TXT proof after bounded target preflight and captures the hostname version, canonical generation, target deployment, current observation, and rollback records.

- Idempotency: required.
- Only one plan may be open for a hostname, and the desired records cannot be expanded or rewritten after creation.

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
POSTGRIP_BODY_FILE="$(mktemp)"
chmod 600 "${POSTGRIP_BODY_FILE}"
trap 'rm -f "${POSTGRIP_BODY_FILE}"' EXIT
cat >"${POSTGRIP_BODY_FILE}" <<'POSTGRIP_JSON'
{
  "expectedCanonicalGeneration": 1,
  "expectedDomainConfigurationVersion": 1,
  "expectedTargetDeploymentId": "11111111-1111-4111-8111-111111111111",
  "kind": "activate",
  "reason": "initial_activation",
  "targetEnvironmentId": "11111111-1111-4111-8111-111111111111",
  "targetProjectId": "11111111-1111-4111-8111-111111111111",
  "ttlSeconds": 30
}
POSTGRIP_JSON
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  POST \
  --header \
  "Content-Type: application/json" \
  --data-binary \
  "@${POSTGRIP_BODY_FILE}" \
  --header \
  "Idempotency-Key: ${POSTGRIP_IDEMPOTENCY_KEY}" \
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
body := strings.NewReader("{\"expectedCanonicalGeneration\":1,\"expectedDomainConfigurationVersion\":1,\"expectedTargetDeploymentId\":\"11111111-1111-4111-8111-111111111111\",\"kind\":\"activate\",\"reason\":\"initial_activation\",\"targetEnvironmentId\":\"11111111-1111-4111-8111-111111111111\",\"targetProjectId\":\"11111111-1111-4111-8111-111111111111\",\"ttlSeconds\":30}")
request, err := http.NewRequestWithContext(ctx, "POST", endpoint.String(), body)
if err != nil { return err }
request.Header.Set("Authorization", "Bearer "+os.Getenv("POSTGRIP_TOKEN"))
request.Header.Set("Content-Type", "application/json")
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
const url = new URL(baseUrl + "/api/v1/services/project/" + encodeURIComponent(process.env.POSTGRIP_SERVICE_ID ?? "") + "/environments/" + encodeURIComponent(process.env.POSTGRIP_ENVIRONMENT_ID ?? "") + "/domains/" + encodeURIComponent(process.env.POSTGRIP_DOMAIN_ID ?? "") + "/dns/plans");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json", "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, },
  body: "{\"expectedCanonicalGeneration\":1,\"expectedDomainConfigurationVersion\":1,\"expectedTargetDeploymentId\":\"11111111-1111-4111-8111-111111111111\",\"kind\":\"activate\",\"reason\":\"initial_activation\",\"targetEnvironmentId\":\"11111111-1111-4111-8111-111111111111\",\"targetProjectId\":\"11111111-1111-4111-8111-111111111111\",\"ttlSeconds\":30}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/project/' + urllib.parse.quote(os.environ['POSTGRIP_SERVICE_ID'], safe='') + '/environments/' + urllib.parse.quote(os.environ['POSTGRIP_ENVIRONMENT_ID'], safe='') + '/domains/' + urllib.parse.quote(os.environ['POSTGRIP_DOMAIN_ID'], safe='') + '/dns/plans'
request = urllib.request.Request(endpoint, data='{"expectedCanonicalGeneration":1,"expectedDomainConfigurationVersion":1,"expectedTargetDeploymentId":"11111111-1111-4111-8111-111111111111","kind":"activate","reason":"initial_activation","targetEnvironmentId":"11111111-1111-4111-8111-111111111111","targetProjectId":"11111111-1111-4111-8111-111111111111","ttlSeconds":30}'.encode(), method='POST')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")
request.add_header('Content-Type', 'application/json')
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
- [deployService](./deployService.md) — Queue a deployment for a confirmed commit
- [previewServiceDeploy](./previewServiceDeploy.md) — Resolve a deploy request to an immutable commit
- [redeployService](./redeployService.md) — Queue a deployment from an existing immutable revision
- [reportServiceDNSProviderResult](./reportServiceDNSProviderResult.md) — Report External DNS Provider Result
- [requestServiceDNSFailover](./requestServiceDNSFailover.md) — Request Canonical DNS Failover

[Back to Service index](./README.md)
