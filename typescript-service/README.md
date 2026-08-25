# PostGrip Service TypeScript SDK

`@postgrip/service` is the typed SDK for PostGrip's public Service API. It uses
a tenant-scoped `pgwm_` management token carrying `services:*` scopes.

```sh
npm install @postgrip/service
```

```ts
import { ServiceClient, referenceFor } from '@postgrip/service';

const client = new ServiceClient({ baseUrl, token });
const service = await client.resolve('api');
const selected = client.forService(referenceFor(service));
const status = await selected.status();

const volumes = await client.administration.volumes.list(projectId);
const impact = await client.administration.projects.removalImpact(projectId);
```

`ServiceClient.fromEnv()` reads `POSTGRIP_WORKERORCHESTRATOR_URL` and
`POSTGRIP_SERVICE_API_TOKEN` in Node environments. Retries are disabled by
default; `enableRetries` plus `retry` can lower the three-attempt, 2-second
backoff, and 30-second `Retry-After` caps but cannot make them unbounded.

Mutations require an explicit `idempotencyKey`. Administration writes also
require the current `ifMatch` ETag. Deletions and worker reassignments use a
fresh impact/preview token; durable worker fan-out returns a configuration
operation available under `client.administration.configurationOperations`.

The administration facade covers targets, projects, environments, managed
volumes, domains, variables, repository settings, promotions, retention, and
configuration operations. Credential values are write-only and never appear
in response types. Call `previewDeploy()` and show the immutable commit to the
operator before calling `deploy()`.

The SDK also exposes async cursor pages, exact environment/deployment lookup,
AbortSignal-aware log following, target/project checks,
redeploy/cancel/rollback, and expected-deployment-fenced start/stop/restart. It
never exposes shell, container, direct database, or secret-read operations.
