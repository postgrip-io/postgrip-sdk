# Unified SDK migration

PostGrip now publishes one artifact per language. Agent, Worker, and Service
are namespaces inside those artifacts rather than separate releases.

| Ecosystem | Unified artifact | Plane namespaces |
| --- | --- | --- |
| Go | `github.com/postgrip-io/postgrip-agent-sdks/go` | `/agent`, `/worker`, `/service` |
| npm | `@postgrip/sdk` | `/agent`, `/worker`, `/service` |
| PyPI | `postgrip` | `.agent`, `.worker`, `.service` |

The published Go module path deliberately retains `postgrip-agent-sdks`.
Do not rewrite it to match the `postgrip-sdks` repository name.

## Authentication

Replace every plane-specific management credential with one
`POSTGRIP_TOKEN`. Replace old orchestrator URL variables with
`POSTGRIP_URL` or the appropriate `POSTGRIP_<PLANE>_URL` override.

Runtime credentials injected by a host Agent are not migrated to the common
token. Keep `POSTGRIP_AGENT_ACCESS_TOKEN`, refresh, expiry, and signing-key
variables host-managed.

## Go imports

```go
// Agent application client
import agent "github.com/postgrip-io/postgrip-agent-sdks/go/agent/client"

// Worker and Service management
import "github.com/postgrip-io/postgrip-agent-sdks/go/worker"
import "github.com/postgrip-io/postgrip-agent-sdks/go/service"

// Infrastructure wire contract
import "github.com/postgrip-io/postgrip-agent-sdks/go/protocol"
```

The protocol, Worker, and Service nested modules no longer have independent
versions. Use the root module version for every import.

## TypeScript imports

```ts
import { PostGrip } from '@postgrip/sdk';
import { Client, Connection, Agent } from '@postgrip/sdk/agent';
import { WorkerClient } from '@postgrip/sdk/worker';
import { ServiceClient } from '@postgrip/sdk/service';
```

## Python imports

```python
from postgrip import PostGrip, AsyncPostGrip
from postgrip.agent import Client, Connection, Agent
from postgrip.worker import WorkerClient
from postgrip.service import ServiceClient
```

## Coordinated release

All ecosystems read the repository `VERSION` and release the same SemVer.
Tags are `go/vX.Y.Z`, `typescript/vX.Y.Z`, and `python/vX.Y.Z`. The server
contract and common-token change deploys before clients are published.

The immutable API reference path contains the exact contract-bundle digest
embedded by the generated clients, so release documentation never silently
tracks a later `main` contract.
