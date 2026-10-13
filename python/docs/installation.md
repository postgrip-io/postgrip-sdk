# Installation

```sh
pip install postgrip
```

To pin a specific version:

```sh
pip install postgrip==0.13.0
```

## Requirements

- **Python 3.11 or newer.** The SDK uses [`asyncio`](https://docs.python.org/3/library/asyncio.html), `contextvars`, and structural typing patterns that target 3.11 / 3.12 / 3.13.
- A reachable PostGrip Agent runtime service. The default address is `https://agentorchestrator1.postgrip.io`.

## Importing

The PyPI distribution and importable root module are both named `postgrip`.
The Agent, Worker, and Service APIs live under singular submodules:

```python
import postgrip.agent
from postgrip.agent import Client, Agent, activity, workflow
from postgrip.worker import WorkerClient
from postgrip.service import ServiceClient
```

The package re-exports its public surface from `postgrip.agent.__init__`, so most code will reach for the top-level names. The lower-level `Connection`, sub-clients (`TaskClient`, `WorkflowClient`, `ScheduleClient`), and wire types (`Task`, `WorkflowExecution`, etc.) are also available there.

## Local development from a clone

```sh
git clone https://github.com/postgrip-io/postgrip-sdk.git
cd postgrip-sdk/python
pip install -e .
PYTHONPATH=src python -m unittest discover -s test
```

The repo uses a `src/` layout, so direct source-tree tests need `PYTHONPATH=src`.
CI also builds and tests the installed wheel without source-tree shadowing.

## Type checking

The package ships with [PEP 561](https://peps.python.org/pep-0561/)-compliant type information (`py.typed` marker file). [mypy](https://mypy-lang.org/) and [pyright](https://github.com/microsoft/pyright) will see the annotations on `Client`, `Agent`, workflow/activity decorators, and every wire type.

## Running against a local agent

For local development, point the SDK at a runtime service running on your machine:

```python
import os
from postgrip.agent import Client

client = await Client.connect(
    "http://127.0.0.1:4100",
    insecure_development=True,  # Explicit local-development opt-in.
    # Common tenant management token with the required Agent scopes.
    auth_token=os.environ["POSTGRIP_TOKEN"],
)
```

When the address is omitted, the connection checks `POSTGRIP_AGENT_URL`, then
`POSTGRIP_URL`, before using the built-in cloud address. For root-facade and
direct-client precedence, see the
[configuration owner](https://github.com/postgrip-io/postgrip-sdk/blob/main/docs/configuration.md).
