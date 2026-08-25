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
```

Mutations require an explicit `idempotencyKey`. Call `previewDeploy()` and show
the immutable commit to the operator before calling `deploy()`.

The SDK also exposes async cursor pages, exact environment/deployment lookup,
AbortSignal-aware log following, target/project checks,
redeploy/cancel/rollback, and expected-deployment-fenced start/stop/restart. It
never exposes shell, container, repository-secret, or environment-secret
operations.
