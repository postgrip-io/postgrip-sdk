# Public resource CRUD parity

Mirror the canonical Agent and Worker contract changes from web's
`docs/design/resource-crud-parity-20261117.md`. Generate bindings and references
for Agent directory/configuration/removal and one-time enrollment, Sandbox
metadata updates, and Worker settings updates. Service CRUD already exists.

Keep enrollment distinct from management authentication: the enrollment key
in the body is its credential, no management bearer is sent, and enrollment
does not retry. The generated low-level endpoint does not install or run a
host Agent; the PostGrip Agent host retains signing keys and runtime sessions.
Machine administration requires the explicit `agent:admin` grant, while
ordinary Agent workload permissions remain unchanged.

Preserve omitted/null fields, Worker idempotency keys, deletion preconditions,
and current Go module/import names. Add explicit TypeScript exports for new
generated names. Exercise observable HTTP requests in all three languages and
run generation, drift, operation inventory/coverage, docs and package checks.
Recorded transport checks are not live evidence. Link the coordinated web PR
and record disposable deployed checks separately before publication.
