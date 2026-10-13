# Keep Agent HTTP response bodies out of default error text

## Problem and scope

Both ordinary Agent HTTP requests and workspace uploads copy arbitrary error
response bodies into SDKError.Message. Applications and the SDK worker log that
message, allowing reflected secrets, forged lines, control characters and large
bodies into ordinary logs.

This slice changes the two Go Agent HTTP error construction paths. Follow
[authentication](../authentication.md), [architecture](../development/architecture.md)
and [validation](../development/testing.md). Other error classes and languages
are outside this finding; this does not claim every SDK error is secret-free.

## Design

Construct both HTTP failure errors through one private helper. The default text
contains the request method, quoted route, numeric status and standard-library
status text only. Do not interpolate the response body or server-provided status
reason. Quoting the route prevents literal control characters in that field.

Preserve SDKError.StatusCode and the exact ResponseBody bytes for explicit
inspection and existing terminal polling logic. Do not remove public fields or
change authentication, routing, success decoding, retry behavior or generated
contracts. Document that ResponseBody can contain secrets and needs caller review
before logging; this is deliberately not a pattern-based secret scrubber.

## Acceptance

Through real local HTTP endpoints, test ordinary and upload failures with
plaintext control characters, synthetic reflected credentials, structured JSON
messages and empty bodies. Assert safe default text and unchanged typed status
and body. Check nonstandard statuses cannot inject a reason phrase and method /
route controls are quoted. Retain successful requests and terminal 410 polling.
Run affected and full Go tests/vet, runtime drift, generated documentation checks,
strict documentation builds and the [PR flow](../development/contributing.md).
