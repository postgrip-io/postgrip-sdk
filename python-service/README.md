# PostGrip Service Python SDK

`postgrip-service` is the typed SDK for PostGrip's public Service API. It uses
a tenant-scoped `pgwm_` management token carrying `services:*` scopes.

```sh
pip install postgrip-service
```

```python
from postgrip_service import ServiceClient, ServiceReference

client = ServiceClient(base_url=base_url, token=token)
service = client.resolve("api")
selected = client.for_service(ServiceReference.from_service(service))
status = selected.status()

volumes = client.administration.managed_volumes.list_service_volumes(project_id)
impact = client.administration.projects.get_service_project_removal_impact(project_id)
```

`ServiceClient.from_env()` and `AsyncServiceClient.from_env()` read
`POSTGRIP_WORKERORCHESTRATOR_URL` and `POSTGRIP_SERVICE_API_TOKEN`. Retries are
disabled by default; the `retry_*` options can lower the three-attempt,
2-second backoff, and 30-second `Retry-After` caps but cannot make them
unbounded.

Mutations require an explicit `idempotency_key`. Generated administration
writes also require the current `if_match` ETag. Deletions and worker
reassignments use a fresh impact/preview token; durable worker fan-out returns a
configuration operation available under
`client.administration.configuration_operations`.

The sync and async administration facades cover targets, projects,
environments, managed volumes, domains, variables, repository settings,
promotions, retention, and configuration operations. Credential values are
write-only and never appear in response types. Call `preview_deploy()` and show
the immutable commit to the operator before calling `deploy()`.

Both sync and async clients expose cursor pages, exact
environment/deployment lookup, cancellable log following, target/project
checks, redeploy/cancel/rollback, and expected-deployment-fenced
start/stop/restart. They never expose shell, container, direct database, or
secret-read operations.
