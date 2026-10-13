# Bounded Go HTTP defaults

## Problem and scope

Ordinary Go Worker and Service requests inherit an unbounded default client.
Agent requests are also unbounded when given a zero-timeout custom client.
Workspace uploads deliberately clear the ordinary timeout, so a background
context permits a stalled exchange to live indefinitely.

This slice changes only Go transport policy. HTTP contracts, generated clients,
wire types, retries and other language implementations do not change. Follow
[architecture](../development/architecture.md),
[configuration](../configuration.md) and [validation](../development/testing.md).

## Design

The shared HTTP client copier supplies a 30-second whole-exchange timeout when
the source timeout is nonpositive. Preserve positive custom timeouts, transports,
cookie jars and redirect checks, and never mutate the supplied client. Agent's
existing RequestTimeout precedence remains: it configures a client only when no
custom HTTPClient is supplied. Earlier context deadlines still win.

Uploads retain their separate lifetime: they do not inherit ordinary request
timeouts. If the supplied context has no deadline, derive a 30-minute context
covering upload and response reads. A caller-supplied deadline, shorter or longer,
is authoritative. This permits the existing 512 MiB archive workflow; applications
on slower links can explicitly choose a longer bounded context. Always cancel
the derived context and preserve redirect protections.

## Acceptance

Exercise default cancellation and existing positive timeouts, including stalled
headers and response bodies. Check all root-client planes receive the policy,
custom clients stay unchanged, and earlier context deadlines win. Exercise upload
default expiry, explicit shorter/longer deadlines and cancellation; retain the
existing upload-outlives-RequestTimeout test. Run Go tests/vet, runtime drift,
generated documentation checks and strict documentation builds, then the shared
[PR review process](../development/contributing.md).
