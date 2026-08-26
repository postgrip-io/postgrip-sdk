# Configuration

Every language implements the same root-client precedence:

1. An explicit constructor value for that plane.
2. `POSTGRIP_AGENT_URL`, `POSTGRIP_WORKER_URL`, or `POSTGRIP_SERVICE_URL`.
3. `POSTGRIP_URL`.

`POSTGRIP_TOKEN` is the only developer-configured management credential.

```sh
export POSTGRIP_URL="https://api.postgrip.io"
export POSTGRIP_TOKEN="pgt_..."
```

Plane overrides are useful for cells, self-hosted routing, and local
integration environments:

```sh
export POSTGRIP_AGENT_URL="https://agents.example.com"
export POSTGRIP_WORKER_URL="https://workers.example.com"
export POSTGRIP_SERVICE_URL="https://services.example.com"
```

Base URLs must use HTTPS, contain no query or fragment, and may include a
reverse-proxy path. Plain HTTP requires the explicit insecure-development
constructor option; it is not enabled by an environment variable. Sandbox
relay overrides follow the same rule: use WSS by default, and permit WS only
when that same insecure-development option is enabled explicitly.

Direct plane clients use the same plane URL and `POSTGRIP_TOKEN` variables.
They do not import or initialize the root facade or another plane.

## Timeouts, retries, and idempotency

The root clients expose common timeout and opt-in retry configuration. Plane
adapters retain operation-specific retry ceilings and only retry operations
the contract marks safe. Mutations that require idempotency must carry a fresh
`Idempotency-Key`; Service administration writes may additionally require the
current `If-Match` value.

Do not blindly retry protocol operations, signed Agent runtime mutations,
archive transfers, or WebSocket sessions. Their generated pages name the
dedicated adapter and conformance runner.
