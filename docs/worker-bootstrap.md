# Durable Worker creation with one PostGrip token

Worker creation uses the same `POSTGRIP_TOKEN` as Agent and Service calls. The
token needs `workers:admin`; no second Worker enrollment or Service management
token is required by the SDK.

`POST /api/v1/workers` accepts caller-generated enrollment and attestation
bootstrap values. Because the API never returns them, reliable automation must
durably persist the exact request and `Idempotency-Key` before sending it. The
`postgrip worker create --request ... --bundle-out ... --yes` CLI is the
recommended implementation: it exclusively writes a mode-`0600` journal,
`fsync`s it before POST, and safely resumes a lost response.

SDK automation may use an approved secret store instead. Persist one closed
record before calling the client:

```json
{
  "schemaVersion": "postgrip.worker-create-sdk/v1",
  "idempotencyKey": "postgrip-worker-create-stable-random-value",
  "request": {
    "name": "worker-us-west-1",
    "host": "https://worker-us-west-1.example.com",
    "autoShutdownOnRemoval": true,
    "bootstrap": {
      "enrollmentKey": "<32 CSPRNG bytes as unpadded base64url>",
      "attestationBootstrapToken": "<32 CSPRNG bytes as unpadded base64url>"
    }
  }
}
```

The two values must each be 43 base64url characters. The journal must be a
regular, non-symlink mode-`0600` file (or an equivalently protected secret-store
record), and its idempotency key and request must be immutable across retries.
After success, atomically persist the safe Worker ID, ETag, and bootstrap
expiries. Never log the journal, enable verbose HTTP traces, or put its values in
process arguments.

## Go

```go
info, err := os.Lstat("worker-create.secret.json")
if err != nil || !info.Mode().IsRegular() || info.Mode()&os.ModeSymlink != 0 || info.Mode().Perm() != 0o600 {
    return errors.New("Worker create journal must be a regular mode-0600 file")
}
var journal struct {
    SchemaVersion  string                     `json:"schemaVersion"`
    IdempotencyKey string                     `json:"idempotencyKey"`
    Request        worker.CreateWorkerRequest `json:"request"`
}
raw, err := os.ReadFile("worker-create.secret.json")
if err != nil { return err }
if err := json.Unmarshal(raw, &journal); err != nil { return err }
if journal.SchemaVersion != "postgrip.worker-create-sdk/v1" { return errors.New("wrong journal schema") }

postgripClient, err := postgrip.NewFromEnv()
if err != nil { return err }
receipt, err := postgripClient.Workers.Create(ctx, journal.Request, journal.IdempotencyKey)
if err != nil { return err } // replay this exact journal after response loss
```

## TypeScript

```ts
import { lstat, readFile } from 'node:fs/promises';
import { PostGrip } from '@postgrip/sdk';
import type { OpenAPICreateWorkerRequest } from '@postgrip/sdk/worker';

const path = 'worker-create.secret.json';
const info = await lstat(path);
if (!info.isFile() || info.isSymbolicLink() || (info.mode & 0o077) !== 0) {
  throw new Error('Worker create journal must be a regular mode-0600 file');
}
const journal = JSON.parse(await readFile(path, 'utf8')) as {
  schemaVersion: 'postgrip.worker-create-sdk/v1';
  idempotencyKey: string;
  request: OpenAPICreateWorkerRequest;
};
if (journal.schemaVersion !== 'postgrip.worker-create-sdk/v1') throw new Error('wrong journal schema');

const postgrip = PostGrip.fromEnv();
const receipt = await postgrip.workers.create(journal.request, {
  idempotencyKey: journal.idempotencyKey,
}); // replay this exact journal after response loss
```

## Python

```python
import json
import os
import stat
from postgrip import PostGrip

path = "worker-create.secret.json"
info = os.lstat(path)
if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
    raise RuntimeError("Worker create journal must be a regular mode-0600 file")
with open(path, encoding="utf-8") as stream:
    journal = json.load(stream)
if journal.get("schemaVersion") != "postgrip.worker-create-sdk/v1":
    raise RuntimeError("wrong journal schema")

postgrip = PostGrip.from_env()
receipt = postgrip.workers.create(
    journal["request"], idempotency_key=journal["idempotencyKey"]
)  # replay this exact journal after response loss
```

See the immutable [`createWorker` API reference](reference/73278af7cf28358c4c7d2fafa3a62b11671d8a1c718fb3bbe6fa1838cb440508/worker/createWorker.md)
for scopes, schemas, replay behavior, errors, and the crash-safe cURL workflow.
