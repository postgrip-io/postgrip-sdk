# Create a schedule

`POST /api/v1/schedules` · `createSchedule` · Agent

> Contract bundle `20dec2d85e3bdbf1943c2e95d09ad184847196c83341e7cc940d33ed156a37fe`
> Agent contract `f29550a4e011d59dd76b398bd364f2c39674a0c47c6428d5a2cfdc2e153bf1c3`

Returns 202. Any tenantId in the body is replaced with the tenant the credential resolves to. An `id` already used by a live (active or paused) schedule answers 409 CONFLICT `schedule already exists`. The `id` of a deleted schedule can be used again: the new schedule replaces the deleted one, and the runs the deleted schedule started keep its `schedule_id` in their history.

## Operation

| Field | Value |
| --- | --- |
| Plane | `agent` |
| Resource tags | `Schedules` |
| Operation class | `tenant-api` |
| Safety | `mutation` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["agent:operate"]]` |
| Idempotency | `none` |
| Retry | `none` |
| Pagination | `none` |

## Parameters

This operation has no path or query parameters.

## Request body

Content type: `application/json` · Schema: `CreateScheduleRequest`

```json
{
  "action": {
    "workflowType": "string"
  },
  "spec": {
    "cron": "0 2 * * *",
    "timezone": "UTC"
  }
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `202` | Schedule | `application/json` | `Schedule` |
| `default` | Request failed | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "action": {
    "workflowType": "string"
  },
  "created_at": "2026-01-01T00:00:00Z",
  "id": "string",
  "namespace": "string",
  "next_run_at": "2026-01-01T00:00:00Z",
  "spec": {
    "cron": "0 2 * * *",
    "timezone": "UTC"
  },
  "state": "active",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Returns 202. Any tenantId in the body is replaced with the tenant the credential resolves to.

- Use isolated fixtures and clean up recorded resource identifiers.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_AGENT_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
POSTGRIP_BODY_FILE="$(mktemp)"
chmod 600 "${POSTGRIP_BODY_FILE}"
trap 'rm -f "${POSTGRIP_BODY_FILE}"' EXIT
cat >"${POSTGRIP_BODY_FILE}" <<'POSTGRIP_JSON'
{
  "action": {
    "workflowType": "string"
  },
  "spec": {
    "cron": "0 2 * * *",
    "timezone": "UTC"
  }
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
  "${POSTGRIP_API_URL}/api/v1/schedules" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_AGENT_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/schedules")
if err != nil { return err }
body := strings.NewReader("{\"action\":{\"workflowType\":\"string\"},\"spec\":{\"cron\":\"0 2 * * *\",\"timezone\":\"UTC\"}}")
request, err := http.NewRequestWithContext(ctx, "POST", endpoint.String(), body)
if err != nil { return err }
request.Header.Set("Authorization", "Bearer "+os.Getenv("POSTGRIP_TOKEN"))
request.Header.Set("Content-Type", "application/json")

client := &http.Client{
    CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
}
response, err := client.Do(request)
```

### TypeScript

```ts
const baseUrl = process.env.POSTGRIP_AGENT_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/api/v1/schedules");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json",  },
  body: "{\"action\":{\"workflowType\":\"string\"},\"spec\":{\"cron\":\"0 2 * * *\",\"timezone\":\"UTC\"}}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_AGENT_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/schedules'
request = urllib.request.Request(endpoint, data='{"action":{"workflowType":"string"},"spec":{"cron":"0 2 * * *","timezone":"UTC"}}'.encode(), method='POST')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")
request.add_header('Content-Type', 'application/json')

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)
```

## Related operations

- [backfillSchedule](./backfillSchedule.md) — Backfill a schedule across a time range
- [deleteSchedule](./deleteSchedule.md) — Delete a schedule
- [getSchedule](./getSchedule.md) — Fetch a single schedule
- [listSchedules](./listSchedules.md) — List schedules
- [pauseSchedule](./pauseSchedule.md) — Pause a schedule
- [triggerSchedule](./triggerSchedule.md) — Run a schedule immediately
- [unpauseSchedule](./unpauseSchedule.md) — Resume a paused schedule
- [updateSchedule](./updateSchedule.md) — Update a schedule

[Back to Agent index](./README.md)
