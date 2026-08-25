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
```

Mutations require an explicit `idempotency_key`. Call `preview_deploy()` and
show the immutable commit to the operator before calling `deploy()`.

Both sync and async clients expose cursor pages, exact
environment/deployment lookup, cancellable log following, target/project
checks, redeploy/cancel/rollback, and expected-deployment-fenced
start/stop/restart. They never expose shell, container, repository-secret, or
environment-secret operations.
