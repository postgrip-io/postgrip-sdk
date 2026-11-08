# Create Managed Target Service

`POST /api/v1/services/targets/managed` · `createManagedTargetService` · Service

> Contract bundle `33186029f5e0ef1b7f6d4c7d1a8ac537828dcea67c8a0520ff273b2add082759`
> Service contract `3ffe1dba1a0a20681bb8b128b80440382e39773d4f324d54e3326c9642b366d8`

Creates a worker-managed PostgreSQL or SQLite database on the Worker `workerId`, as the console's **+ Add Service** → **PostgreSQL** or **SQLite** → **Add (worker-managed)** does: the Worker creates a Docker volume from `volumeName` and starts the database's container on it. For `postgresql`, `imageRef` is an image from `listServicePostgreSQLImages` for the Worker's architecture, and the Worker generates the database password, which never leaves it: there is no password to send, and `putTargetServiceConnection` is not needed. The answer comes once the Worker has created the database and, for PostgreSQL, the database answers; the first create on a Worker can take a few minutes while it pulls the image. If the Worker has not answered by then, the answer is `409` `IDEMPOTENCY_IN_PROGRESS` (or `SERVICE_CREATION_PENDING`) and the key is not kept: send the same request with the same Idempotency-Key, which continues the same create and never creates a second database, within 24 hours. Follow it with `getServiceStatus` or `checkService`. Remove it with `detachTargetService` (`dataDisposition`).

## Operation

| Field | Value |
| --- | --- |
| Plane | `service` |
| Resource tags | `Administration` |
| Operation class | `tenant-api` |
| Safety | `mutation` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["services:admin"]]` |
| Idempotency | `required` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `Idempotency-Key` | header | yes | `string` | `"recorded"` | — |
| `If-Match` | header | yes | `string` | `"string"` | — |

## Request body

Content type: `application/json` · Schema: `CreateManagedTargetServiceRequest`

```json
{
  "kind": "postgresql",
  "name": "string",
  "slug": "string",
  "volumeName": "string",
  "workerId": "11111111-1111-4111-8111-111111111111"
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `201` | The database was created and is running on the Worker. | `application/json` | `CreateManagedTargetServiceResponse` |
| `400` | `VALIDATION`: a field breaks a rule of `CreateManagedTargetServiceRequest`, `imageRef` is not in the catalog or not for the Worker's architecture, or the Worker refused the settings; `message` names the field. `SQLITE_PATH_NOT_ALLOWED`: the Worker refused the SQLite database's path. `INVALID_BODY`: the body is not valid JSON, has a field the call does not accept or a value of the wrong type, or lacks `kind`, `workerId`, `name`, `slug` or `volumeName`. | `application/json` | `ErrorResponse` |
| `403` | `INSUFFICIENT_SCOPE`: the token lacks `services:admin` (`details.requiredScope`). `FORBIDDEN`: the Worker's own policy refused to create the database; what it had created and the service are removed. | `application/json` | `ErrorResponse` |
| `404` | `NOT_FOUND`: `workerId` is not a Worker of the organization, or it was removed or replaced. `SERVICE_NOT_FOUND`: `appId` is not an application of the organization. | `application/json` | `ErrorResponse` |
| `409` | Conflict. `SERVICE_STATE_CHANGED`: a service with that `slug` already exists. `WORKER_REVOKED`: the Worker is revoked (`details.workerId`). `WORKER_UPGRADE_REQUIRED`: the Worker is too old to create a managed database; upgrade it. When the Worker read finds it (`details.requiredCapability`), this refusal is not kept under the Idempotency-Key, so a retry with the same key runs again; when the create itself finds it, it is kept: send a new key after the upgrade. `MANAGED_POSTGRES_ERROR`, `MANAGED_SQLITE_ERROR`, `TARGET_CONFLICT`, `WORKER_REFUSED`: the Worker could not create the database; what it had created and the service are removed. `TARGET_REMOVED`: the Worker was removed while the database was being created. `SERVICE_CREATION_PENDING`: something was sent to the Worker, which then stopped being live or must be upgraded; the create stays pending (`details.serviceId`, `details.cause`) and the key is not kept: resend with the same key once the Worker is back. `IDEMPOTENCY_IN_PROGRESS`: the create is still running, or the Worker has not answered yet (`Retry-After`); the key is not kept: resend with the same key. `IDEMPOTENCY_CONFLICT`: the key was used with a different request. | `application/json` | `ErrorResponse` |
| `410` | `CREATION_RESOURCE_DELETED`: the service was deleted while it was being created, or after; nothing is created again. | `application/json` | `ErrorResponse` |
| `412` | `PRECONDITION_FAILED`: `If-Match` is not the service catalog's current ETag (`details.currentVersion`). Read the catalog again (`listServices`, `catalogEtag`) and send a new key. | `application/json` | `ErrorResponse` |
| `428` | `PRECONDITION_REQUIRED`: the `If-Match` header is missing. | `application/json` | `ErrorResponse` |
| `502` | `IMAGE_CATALOG_UNAVAILABLE`: the official PostgreSQL image catalog could not be read; retry. `WORKER_ERROR`: the Worker gave an answer PostGrip does not know. | `application/json` | `ErrorResponse` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "configurationRevision": 1,
  "receipt": {
    "auditRecorded": true,
    "replayed": true,
    "requestId": "string"
  },
  "target": {
    "createdAt": "2026-01-01T00:00:00Z",
    "databaseName": "string",
    "etag": "string",
    "hasConnectionSecret": true,
    "host": "string",
    "id": "11111111-1111-4111-8111-111111111111",
    "managed": true,
    "name": "string",
    "port": 1,
    "ref": "string",
    "slug": "string",
    "ssl": true,
    "updatedAt": "2026-01-01T00:00:00Z",
    "version": 1,
    "workerId": "11111111-1111-4111-8111-111111111111"
  }
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Creates a worker-managed PostgreSQL or SQLite through the console's keyed create: the Worker creates the volume and container and, for PostgreSQL, waits for the database before the 201 answers target, configurationRevision and receipt. The request carries no password; the Worker derives it and keeps it.

- Idempotency: required.
- If-Match: required (the service catalog ETag).
- Use isolated fixtures and clean up recorded resource identifiers.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_IDEMPOTENCY_KEY:?set POSTGRIP_IDEMPOTENCY_KEY for this request}"
: "${POSTGRIP_IF_MATCH:?set POSTGRIP_IF_MATCH for this request}"
POSTGRIP_BODY_FILE="$(mktemp)"
chmod 600 "${POSTGRIP_BODY_FILE}"
trap 'rm -f "${POSTGRIP_BODY_FILE}"' EXIT
cat >"${POSTGRIP_BODY_FILE}" <<'POSTGRIP_JSON'
{
  "kind": "postgresql",
  "name": "string",
  "slug": "string",
  "volumeName": "string",
  "workerId": "11111111-1111-4111-8111-111111111111"
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
  --header \
  "If-Match: ${POSTGRIP_IF_MATCH}" \
  "${POSTGRIP_API_URL}/api/v1/services/targets/managed" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/targets/managed")
if err != nil { return err }
body := strings.NewReader("{\"kind\":\"postgresql\",\"name\":\"string\",\"slug\":\"string\",\"volumeName\":\"string\",\"workerId\":\"11111111-1111-4111-8111-111111111111\"}")
request, err := http.NewRequestWithContext(ctx, "POST", endpoint.String(), body)
if err != nil { return err }
request.Header.Set("Authorization", "Bearer "+os.Getenv("POSTGRIP_TOKEN"))
request.Header.Set("Content-Type", "application/json")
request.Header.Set("Idempotency-Key", os.Getenv("POSTGRIP_IDEMPOTENCY_KEY"))
request.Header.Set("If-Match", os.Getenv("POSTGRIP_IF_MATCH"))
client := &http.Client{
    CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
}
response, err := client.Do(request)
```

### TypeScript

```ts
const baseUrl = process.env.POSTGRIP_SERVICE_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/api/v1/services/targets/managed");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json", "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, "If-Match": process.env.POSTGRIP_IF_MATCH, },
  body: "{\"kind\":\"postgresql\",\"name\":\"string\",\"slug\":\"string\",\"volumeName\":\"string\",\"workerId\":\"11111111-1111-4111-8111-111111111111\"}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/targets/managed'
request = urllib.request.Request(endpoint, data='{"kind":"postgresql","name":"string","slug":"string","volumeName":"string","workerId":"11111111-1111-4111-8111-111111111111"}'.encode(), method='POST')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")
request.add_header('Content-Type', 'application/json')
request.add_header('Idempotency-Key', os.environ["POSTGRIP_IDEMPOTENCY_KEY"])
request.add_header('If-Match', os.environ["POSTGRIP_IF_MATCH"])
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)
```

## Related operations

- [abandonServiceConfigurationOperation](./abandonServiceConfigurationOperation.md) — Abandon Service Configuration Operation
- [adoptGitHubRepository](./adoptGitHubRepository.md) — Adopt GitHub Repository
- [applyPostGripConfigurationPlan](./applyPostGripConfigurationPlan.md) — Apply PostGrip Configuration Plan
- [applyServiceVariables](./applyServiceVariables.md) — Apply Service Variables
- [attachTargetService](./attachTargetService.md) — Attach Target Service
- [bindServiceVolume](./bindServiceVolume.md) — Bind Service Volume
- [clearServiceRepositoryCredential](./clearServiceRepositoryCredential.md) — Clear Service Repository Credential
- [clearServiceVariableValue](./clearServiceVariableValue.md) — Clear Service Variable Value

[Back to Service index](./README.md)
