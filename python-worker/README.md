# PostGrip Worker Python SDK

`postgrip-worker` is the typed client for PostGrip's public Worker management
API. It uses a dedicated `pgwm_` token and never shares Agent runtime sessions.

```python
from postgrip_worker import AsyncWorkerClient

client = AsyncWorkerClient(base_url="https://worker.example.com", token="pgwm_...")
worker = await client.get("worker-id")
```
