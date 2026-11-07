# Managed runtime Agent address

## Problem and scope

A host PostGrip Agent launches each `workflow.runtime` task with
`POSTGRIP_AGENT_MANAGED_RUNTIME=true` and the address of its Agent Orchestrator
in `POSTGRIP_AGENTORCHESTRATOR_URL`, beside the delegated `POSTGRIP_AGENT_*`
session (web's
`postgrip-agent/internal/agenttaskexecutionservice/workflow_environment_service.go`).
Agent connections in all three SDKs read only `POSTGRIP_AGENT_URL`, then
`POSTGRIP_URL`, then the built-in cloud address. On any installation with
another orchestrator, a runtime started with only the host-injected variables
polls the wrong host. The task cannot correct it: the host Agent refuses
`POSTGRIP_*` names in a `workflow.runtime` payload's `env`.

This slice changes only the address an Agent connection resolves when none is
passed. HTTP contracts, generated clients, wire types, credentials and the root
facades, which require a management token and pass their resolved plane URL
explicitly, do not change. Follow [architecture](../development/architecture.md),
[configuration](../configuration.md) and [validation](../development/testing.md).

## Design

Each Agent connection resolves its base URL from the first configured value of
the following, keeping each SDK's existing treatment of empty variables:

1. the explicit address option (`Address`, `baseUrl`, `address`);
2. `POSTGRIP_AGENTORCHESTRATOR_URL`, only when `POSTGRIP_AGENT_MANAGED_RUNTIME`
   is exactly `true`, matching how each SDK's Agent detects a managed runtime;
3. `POSTGRIP_AGENT_URL`;
4. `POSTGRIP_URL`;
5. the built-in cloud address.

The orchestrator variable is ignored outside a managed runtime, so ordinary
applications keep their current precedence. An explicit option still wins, so
callers that deliberately choose an address are unaffected. The resolved value
passes the existing base-URL validation unchanged, including the HTTPS rule and
its explicit insecure-development opt-in.

Keep the lookup in one small resolver beside each connection constructor: Go's
`NewConnection`, TypeScript's `Connection.create` and Python's `Connection`.

## Acceptance

In each SDK, unit-test that a managed runtime with only the host-injected
address connects to `POSTGRIP_AGENTORCHESTRATOR_URL` ahead of
`POSTGRIP_AGENT_URL` and `POSTGRIP_URL`; that an explicit option still wins;
and that outside a managed runtime the orchestrator variable is ignored and
`POSTGRIP_AGENT_URL`, `POSTGRIP_URL` and the default keep their order. Update
the [configuration owner](../configuration.md), the language installation
guides that restate the lookup, and each SDK's unreleased release notes. Run
each SDK's suite, then the shared [PR review process](../development/contributing.md).

## Examples

The bundled Go, TypeScript and Python examples (`greeting` and `longrun`)
connect with no address in their managed-runtime branch, so they reach the
host-injected orchestrator through the lookup above. Their submitting branch,
which runs outside a managed runtime, keeps its explicit address.
