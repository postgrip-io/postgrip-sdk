# Secure cURL usage

The generated API reference includes cURL for every eligible management
operation. Examples require cURL 7.76 or newer for `--fail-with-body`.

Disable shell tracing and send the bearer through a cURL configuration on
standard input:

```sh
set +x
curl --config - \
  --fail-with-body --silent --show-error \
  "${POSTGRIP_URL}/api/v1/services" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

The expanded token is not present in cURL's argument vector. It can still be
observed by a privileged local process through inherited environment state, so
run automation on a trusted host and unset the token when the process no
longer needs it.

## Mutations

Generated request bodies use mode-0600 temporary files that are removed by a
shell trap. Their values are illustrative only. Required path, query,
idempotency, and ETag values use named environment variables:

```sh
export POSTGRIP_SERVICE_ID="11111111-1111-4111-8111-111111111111"
export POSTGRIP_IDEMPOTENCY_KEY="deploy-$(date +%s)-$$"
export POSTGRIP_IF_MATCH='"revision:7"'
```

Path variables must already be percent-encoded in shell cURL examples. Do not
put credentials, repository secrets, or variable values in process arguments.
The generated temporary-file pattern keeps request bodies out of cURL's
argument vector and removes the protected file when the shell exits.

## Protocol exceptions

Signed Agent runtime mutations, long polling, archive streaming, session
refresh, and WebSocket framing use dedicated SDK adapters and conformance
runners. Their pages explain why a stock cURL command is incomplete and do not
present unsigned or unframed language snippets as valid calls.

Start with the [current immutable reference](reference/README.md).
