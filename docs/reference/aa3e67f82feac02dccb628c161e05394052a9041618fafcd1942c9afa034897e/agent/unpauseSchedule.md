# Resume a paused schedule

`POST /api/v1/schedules/{scheduleId}/unpause` · `unpauseSchedule` · Agent

> Contract bundle `aa3e67f82feac02dccb628c161e05394052a9041618fafcd1942c9afa034897e`
> Agent contract `86aa7d831437544f83f26486212b297565f621d784f2850c5c9af391e3f68018`

Uses the contract-defined POST /api/v1/schedules/{scheduleId}/unpause behavior.

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

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `scheduleId` | path | yes | `string` | `"string"` | — |

## Request body

Content type: `application/json` · Schema: `UnpauseScheduleRequest`

```json
{
  "reason": "string"
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Schedule | `application/json` | `Schedule` |
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

Uses the contract-defined POST /api/v1/schedules/{scheduleId}/unpause behavior.

- Use isolated fixtures and clean up recorded resource identifiers.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_AGENT_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_SCHEDULE_ID:?set POSTGRIP_SCHEDULE_ID to a percent-encoded path value}"
POSTGRIP_BODY_FILE="$(mktemp)"
chmod 600 "${POSTGRIP_BODY_FILE}"
trap 'rm -f "${POSTGRIP_BODY_FILE}"' EXIT
cat >"${POSTGRIP_BODY_FILE}" <<'POSTGRIP_JSON'
{
  "reason": "string"
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
  "${POSTGRIP_API_URL}/api/v1/schedules/${POSTGRIP_SCHEDULE_ID}/unpause" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_AGENT_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/schedules/" + url.PathEscape(os.Getenv("POSTGRIP_SCHEDULE_ID")) + "/unpause")
if err != nil { return err }
body := strings.NewReader("{\"reason\":\"string\"}")
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
const url = new URL(baseUrl + "/api/v1/schedules/" + encodeURIComponent(process.env.POSTGRIP_SCHEDULE_ID ?? "") + "/unpause");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json",  },
  body: "{\"reason\":\"string\"}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_AGENT_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/schedules/' + urllib.parse.quote(os.environ['POSTGRIP_SCHEDULE_ID'], safe='') + '/unpause'
request = urllib.request.Request(endpoint, data='{"reason":"string"}'.encode(), method='POST')
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
- [createSchedule](./createSchedule.md) — Create a schedule
- [deleteSchedule](./deleteSchedule.md) — Delete a schedule
- [getSchedule](./getSchedule.md) — Fetch a single schedule
- [listSchedules](./listSchedules.md) — List schedules
- [pauseSchedule](./pauseSchedule.md) — Pause a schedule
- [triggerSchedule](./triggerSchedule.md) — Run a schedule immediately
- [updateSchedule](./updateSchedule.md) — Update a schedule

[Back to Agent index](./README.md)
