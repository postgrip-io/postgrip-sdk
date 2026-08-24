# PostGrip Worker TypeScript SDK

`@postgrip/worker` is the typed client for PostGrip's public Worker management
API. It uses a dedicated `pgwm_` token and never shares Agent runtime sessions.

```ts
import { WorkerClient } from '@postgrip/worker';

const workers = new WorkerClient({ baseUrl, token });
for await (const entry of workers.operationalLogs.follow(workerId)) {
  console.log(entry.message);
}
```
