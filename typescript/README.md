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
common URL, while explicit constructor values override the environment.

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
reference](../docs/reference/e53278e3f9a421f682e65bf9f84baa0bb8f76225cd317197eb522ff567505650/README.md).
Durable public Worker creation is covered in the [Worker bootstrap
guide](../docs/worker-bootstrap.md).

```sh
bun install --frozen-lockfile
bun run typecheck
bun run build
bun run test
npm pack --dry-run
```
