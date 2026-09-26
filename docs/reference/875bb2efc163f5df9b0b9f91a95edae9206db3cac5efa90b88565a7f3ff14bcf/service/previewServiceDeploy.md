# Resolve a deploy request to an immutable commit

`GET /api/v1/services/project/{serviceId}/deploy/preview` · `previewServiceDeploy` · Service

> Contract bundle `875bb2efc163f5df9b0b9f91a95edae9206db3cac5efa90b88565a7f3ff14bcf`
> Service contract `255550d7cb8a8c6662ad1b7944412d9cca4e5d1c0f181a002770e776c1d9b158`

Resolves a deploy request to an environment and the immutable head commit of its branch, which deployService then confirms as `expectedCommitSha`. For a private GitHub service bound to no GitHub installation, and for GitLab and Bitbucket services, the service's repository credential is held only by its Workers, so the environment's Worker reads the branch head with it and returns only the commit. The preview fails with `409` `WORKER_UPGRADE_REQUIRED` (with `details.workerId` and `details.requiredCapability: "repository_head_read_v1"`) when that Worker must be upgraded first, `409` `NO_ELIGIBLE_WORKER` when no Worker can read it, and `409` `REPOSITORY_CREDENTIAL_UNAVAILABLE` when the Worker's credential cannot read the repository. The message then names what the target Worker needs: while a supplied credential is being delivered, wait for it; when it awaits resubmission, resubmit it; with none, or one the repository refuses, supply one (or bind the service to a GitHub account). To deploy a commit without reading the branch head, send it to deployService with `namedCommit: true`.

## Operation

| Field | Value |
| --- | --- |
| Plane | `service` |
| Resource tags | `Operations` |
| Operation class | `tenant-api` |
| Safety | `read-only` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["services:operate"]]` |
| Idempotency | `none` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `serviceId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `environment` | query | no | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `branch` | query | no | `string` | `"string"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Deploy preview | `application/json` | `DeployPreview` |
| `409` | Conflict. `REPOSITORY_CREDENTIAL_UNAVAILABLE`: PostGrip cannot obtain the credential it needs to read the branch head, or the Worker that holds the service's credential cannot read the repository with it (the message names what the target Worker needs). `WORKER_UPGRADE_REQUIRED`: the Worker that must read the head does not advertise `repository_head_read_v1` (`details.workerId`, `details.requiredCapability`). `NO_ELIGIBLE_WORKER`: no Worker can read the head. Other conflicts, such as `SERVICE_OPERATION_NOT_SUPPORTED` and `SERVICE_ENVIRONMENT_REQUIRED`, also use this status. | `application/json` | `ErrorResponse` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "branch": "string",
  "commitSha": "string",
  "environmentId": "11111111-1111-4111-8111-111111111111",
  "environmentName": "string",
  "serviceRef": "string"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Uses the contract-defined GET /api/v1/services/project/{serviceId}/deploy/preview behavior.

- No additional lifecycle constraint is recorded.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_SERVICE_ID:?set POSTGRIP_SERVICE_ID to a percent-encoded path value}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  GET \
  "${POSTGRIP_API_URL}/api/v1/services/project/${POSTGRIP_SERVICE_ID}/deploy/preview" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/project/" + url.PathEscape(os.Getenv("POSTGRIP_SERVICE_ID")) + "/deploy/preview")
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
const url = new URL(baseUrl + "/api/v1/services/project/" + encodeURIComponent(process.env.POSTGRIP_SERVICE_ID ?? "") + "/deploy/preview");

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/project/' + urllib.parse.quote(os.environ['POSTGRIP_SERVICE_ID'], safe='') + '/deploy/preview'
request = urllib.request.Request(endpoint, method='GET')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")


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
- [redeployService](./redeployService.md) — Queue a deployment from an existing immutable revision
- [reportServiceDNSProviderResult](./reportServiceDNSProviderResult.md) — Report External DNS Provider Result
- [requestServiceDNSFailover](./requestServiceDNSFailover.md) — Request Canonical DNS Failover

[Back to Service index](./README.md)
