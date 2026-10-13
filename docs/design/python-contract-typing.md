# Python contract typing

Date: 2026-10-13. Status: proposed.

## Problem and boundaries

The Python package ships `py.typed`, so its annotations are part of the public
contract. The SDK architecture audit of `main` at `3675b2f2` found two places
where Python typing loses shapes the OpenAPI contracts define:

- **Generated nested objects.** `scripts/generate_openapi.py:python_schema_type`
  returns `dict[str, Any]` for any inline object property, even when the
  property is closed (`additionalProperties: false`) with declared
  `properties`. Every case is in Service: 12 closed inline objects under
  `ServiceBuildLogStatus`, `ServiceRuntimeLogWorkerStatus`,
  `ServiceBuildLogSettingsMutationResponse`, `ServiceBuildLogMaintenanceResponse`
  and the two `oneOf` branches of `PostGripConfigurationWorkerSelector`.
  Agent and Worker inline objects are all open maps
  (`additionalProperties: {schema}`) and already map to `dict[str, T]`.
- **Agent convenience signatures.** `python/src/postgrip/agent/types.py` already
  aliases the generated TypedDicts (`Task`, `EnqueueTaskRequest`, `Schedule`,
  …). Yet `Connection.enqueue_task`, `get_task`, the workflow, schedule and
  task-event methods, `Client` and `WorkflowClient` helpers and `SandboxClient`
  accept and return `dict[str, Any]`, lists of it, or untyped `**options`, even
  where they immediately call a precisely typed generated operation.

This design changes annotations and generated TypedDict declarations only.
Runtime behavior, request bytes, validation, contracts, wire types and the Go
and TypeScript SDKs do not change. TypedDicts remain static shapes; they are not
runtime validators. Follow [contracts](../development/contracts.md),
[architecture](../development/architecture.md) and [validation](../development/testing.md).

## Design

### Nested generated TypedDicts

`python_schema_type` receives the name of the declaration that contains a
schema. For a closed inline object (`additionalProperties: false`) with
`properties`, the generator emits a named TypedDict and returns its name
instead of `dict[str, Any]`:

- The name is the parent declaration plus the property in PascalCase, for
  example `_SchemaServiceBuildLogStatusStatus` and
  `_SchemaServiceBuildLogStatusStatusSettings`. Array items add `Item`, and
  `oneOf` and `anyOf` branches add `Alternative{n}`. A name that collides with
  an existing declaration fails generation instead of being renamed silently.
- Requiredness follows the schema's `required` list, using the same
  required-plus-`total=False` base pattern as top-level objects. Nested objects
  are handled recursively.
- `additionalProperties: {schema}` without `properties` stays
  `dict[str, T]`. Any other object that does not set
  `additionalProperties: false` stays `dict[str, Any]`, because the contract
  permits arbitrary keys there and a Python 3.11 TypedDict cannot express
  extra keys. No such property-bearing open inline object exists today.

Nested declarations are emitted before the declaration that uses them, and they
are not added to the public `OpenAPI*` alias list. They are reachable through
the existing public aliases, and the plane `__init__` exports stay unchanged.

### Typed Agent signatures

Agent convenience methods use the generated aliases from `types.py`:

- Request parameters and return values use the matching aliases, for example
  `enqueue_task(request: EnqueueTaskRequest) -> Task`,
  `get_task(...) -> Task`, `list_tasks(...) -> list[Task]`,
  `get_workflow(...) -> WorkflowExecution`,
  `create_schedule(request: CreateScheduleRequest) -> Schedule`,
  `poll_task_response(...) -> PollTaskResponse`, and the task-event and history
  methods returning `TaskEvent` and `WorkflowHistoryEvent`. Where `types.py`
  lacks an alias for an operation's type, add one from the generated module.
- `**options` keyword arguments are typed with `Unpack[...]` over a TypedDict
  of the options each method already accepts, such as `ListTasksOptions`. The
  accepted keyword names and call syntax do not change.
- User-defined data stays open: workflow and activity `args` remain
  `list[Any]`, and payload, memo, search-attribute and result values keep the
  generated `JsonValue` or `Any` types. Only the envelope is typed.
- Async wrappers mirror their synchronous counterparts' annotations.

New option TypedDicts live in `types.py` and are exported from
`postgrip.agent` beside the existing aliases, so callers can annotate their
own option dictionaries.

## Compatibility

No runtime behavior, name or request changes. Static type checkers become
stricter. Code that passes a variable annotated `dict[str, Any]` where a request
TypedDict is now expected, or that reads an undeclared key from a typed
response, reports new type errors. Dictionary literals with the declared keys
keep type-checking. Release notes call out the stricter annotations.

## Delivery slices

1. **Nested TypedDicts.** Change the generator, regenerate the Python bindings,
   and extend the generator's checks.
2. **Typed Agent signatures.** Annotate the Agent `Connection`, `Client`,
   workflow, schedule, task and sandbox convenience methods, and add the option
   TypedDicts.

Each slice is its own PR under the [review process](../development/contributing.md)
and updates `python/docs/api.md` where it documents changed signatures.

## Acceptance

The repository has no static type checker in CI, so tests check annotations at
runtime with `typing.get_type_hints`:

- Slice 1: every closed inline object in the three generated Python modules
  resolves to a TypedDict whose keys, required keys and nested types match the
  contract. A generator test walks the contracts and fails when any closed
  object schema with `properties` maps to `dict[str, Any]`. `generate_openapi.py
  --check`, the endpoint runners and the Python suite pass, and Agent and Worker
  bindings are unchanged.
- Slice 2: for each annotated method, the hints resolve to the intended aliases.
  The `Unpack` option TypedDicts list exactly the keywords the method forwards.
  Existing Agent tests and the recorded endpoint and cURL runners pass
  unchanged.
