# PostGrip TypeScript SDK

Install the one npm package:

```sh
npm install @postgrip/sdk
```

```ts
import { PostGrip } from '@postgrip/sdk';

const postgrip = PostGrip.fromEnv();
const tasks = await postgrip.agent.task.list();
const workers = await postgrip.workers.list();
const services = await postgrip.services.list();
```

Configure `POSTGRIP_URL` and `POSTGRIP_TOKEN`. Optional plane URLs override the
common URL. See [configuration](../docs/configuration.md) for the precedence of
explicit plane URLs, environment plane URLs and the common constructor URL.

The package exports isolated singular subpaths with runtime and declaration
entries:

```ts
import { Client, Connection, Agent } from '@postgrip/sdk/agent';
import { WorkerClient } from '@postgrip/sdk/worker';
import { ServiceClient } from '@postgrip/sdk/service';
```

Importing a management subpath does not evaluate Agent runtime or WebSocket
code. Agent sandbox WebSocket support remains included through the Agent
subpath.

See the repository [quick start](../README.md), [authentication
model](../docs/authentication.md), and [generated API
reference](../docs/reference/eaa33d8443f0431112bc1e9d35ee4150803d180042771015feb41a8b00ab99da/README.md).
Durable public Worker creation is covered in the [Worker bootstrap
guide](../docs/worker-bootstrap.md).

```sh
bun install --frozen-lockfile
bun run typecheck
bun run build
bun run test
npm pack --dry-run
```
