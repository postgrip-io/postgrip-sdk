# Python cancellation-aware HTTPS on Python 3.12+

## Problem and scope

`CancellationAwareHTTPSHandler` in `python/src/postgrip/_internal/http.py`
always passes `check_hostname=` to `HTTPSConnection`. Python 3.12 removed that
argument. It also removed `HTTPSHandler._check_hostname`, applying the setting
to the SSL context instead. On Python 3.12 and 3.13 every HTTPS request through
the handler raises `TypeError`. The Worker, Service and Agent clients all
compose this handler, so none of them can reach an HTTPS endpoint on those
versions. CI did not detect it because the local test servers use plain HTTP.

This slice changes only how that handler opens HTTPS connections. Cancellation,
redirect policy, timeouts, response bounds and TLS verification do not change.
Follow [architecture](../development/architecture.md) and
[validation](../development/testing.md).

## Design

The handler forwards `context` as the standard library's `HTTPSHandler` does.
It forwards `check_hostname` only when the running standard library still
records it (`_check_hostname` set, which is Python 3.11). On 3.12 and later the
inherited constructor has already applied the setting to the context. TLS
verification therefore matches the stdlib handler on every supported version.

## Acceptance

Against a local TLS server with a self-signed certificate trusted by the client
context:

- an opener built from the handler completes a request;
- a client context that does not trust the certificate still fails
  verification;
- a `WorkerClient` given a trusting opener completes a request end to end.

These tests fail with `TypeError` before the fix on Python 3.12, and CI runs
them on 3.11, 3.12 and 3.13. Existing Python tests and the recorded endpoint
runners pass unchanged.
