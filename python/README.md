# PostGrip Python SDK

Install the one PyPI distribution:

```sh
pip install postgrip
```

```python
from postgrip import PostGrip

postgrip = PostGrip.from_env()
tasks = postgrip.agent.task.list()
workers = postgrip.workers.list()
services = postgrip.services.list()
```

Async Worker and Service management is available from the same package:

```python
from postgrip import AsyncPostGrip

async with AsyncPostGrip.from_env() as postgrip:
    workers = await postgrip.workers.list()
    services = await postgrip.services.list()
```

Direct modules remain independently importable:

```python
from postgrip.agent import Client, Connection, Agent
from postgrip.worker import WorkerClient, AsyncWorkerClient
from postgrip.service import ServiceClient, AsyncServiceClient
```

The distribution contains one `py.typed` marker. `cryptography` remains a base
dependency for Agent signing; interactive sandbox WebSockets use the optional
`postgrip[sandbox]` extra and are not loaded by Worker or Service imports.

See the repository [quick start](../README.md), [authentication
model](../docs/authentication.md), and [generated API
reference](../docs/reference/bec2f2e5a97835b4ac053b2734e9431ed1df6e00b453393626212cc32a2f7e1b/README.md).
Durable public Worker creation is covered in the [Worker bootstrap
guide](../docs/worker-bootstrap.md).

```sh
PYTHONPATH=src python3 -m unittest discover -s test
uv build --wheel
```
