"""Host-launched source fixture for SDK #152; no management credentials."""
import asyncio
import json
import os
import time
import uuid
import signal
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python" / "src"))
from postgrip.agent import Agent, Client, Connection, activity, workflow


@activity.defn(name="auditCancellation")
async def audit_cancellation(identifier: str) -> str:
    print(json.dumps({"audit": identifier}), flush=True)
    return "audit:" + identifier


@workflow.defn(name="CancellationCleanup")
class CancellationCleanup:
    @workflow.run
    async def run(self, identifier: str) -> str:
        try:
            await workflow.sleep(timedelta(days=1))
            return "expired"
        finally:
            if workflow.cancellation_requested():
                async def cleanup():
                    await workflow.execute_activity("auditCancellation", identifier)
                await workflow.CancellationScope.non_cancellable(cleanup)


async def main():
    connection = await Connection.connect()
    agent = Agent(connection=connection, workflows=[CancellationCleanup], activities=[audit_cancellation])
    signal.signal(signal.SIGTERM, lambda *_: agent.shutdown(timeout=5))
    async def until(read, predicate):
        end = time.monotonic() + 90
        while time.monotonic() < end:
            value = await read()
            if predicate(value):
                return value
            await asyncio.sleep(0.25)
        raise RuntimeError("live cancellation check timed out")

    async def scenario():
        identifier = "sdk152-python-" + str(uuid.uuid4())
        handle = await Client(connection).start_workflow("CancellationCleanup", identifier,
            id=identifier, task_queue=os.environ["POSTGRIP_AGENT_TASK_QUEUE"], workflow_run_timeout=timedelta(minutes=3))
        try:
            await until(handle.history, lambda h: any(e["type"] == "TimerStarted" for e in h))
            execution = await asyncio.to_thread(connection.get_workflow, handle.run_id or identifier)
            async def read_task():
                return await asyncio.to_thread(connection.get_task, execution["task_id"])
            await until(read_task, lambda t: t["state"] == "blocked")
            await handle.cancel("SDK #152 live cancellation")
            task = await until(read_task, lambda t: t["state"] in ("failed", "succeeded"))
            history = await handle.history()
            assert task["state"] == "failed", task["state"]
            assert task["result"]["failure"]["type"] == "CancelledFailure", task.get("error")
            cleanups = [e for e in history if e["type"] == "ActivityTaskScheduled" and e.get("attributes", {}).get("activity_type") == "auditCancellation"]
            assert len(cleanups) == 1
            cleanup = await asyncio.to_thread(connection.get_task, cleanups[0]["task_id"])
            assert cleanup["state"] == "succeeded"
            assert cleanup["result"]["value"] == "audit:" + identifier
            print(json.dumps({"language": "python", "workflowId": identifier, "runId": handle.run_id, "cleanup": cleanup["id"], "cleanupResult": cleanup["result"]["value"], "failure": task["result"]["failure"], "historyTypes": [e["type"] for e in history]}), flush=True)
        finally:
            execution = await asyncio.to_thread(connection.get_workflow, handle.run_id or identifier)
            task = await asyncio.to_thread(connection.get_task, execution["task_id"])
            if task["state"] not in ("failed", "succeeded"):
                await handle.terminate("SDK #152 fixture cleanup")

    await agent.run_until(scenario())


if __name__ == "__main__":
    asyncio.run(main())
