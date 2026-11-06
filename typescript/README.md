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
reference](../docs/reference/8031543651e185f63f1155ec3cc236fa1f91f292aac0b1d2ee101ace74f52a39/README.md).
Durable public Worker creation is covered in the [Worker bootstrap
guide](../docs/worker-bootstrap.md).

```sh
bun install --frozen-lockfile
bun run typecheck
bun run build
bun run test
npm pack --dry-run
```
