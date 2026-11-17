from __future__ import annotations

import asyncio
import unittest
from datetime import timedelta
from unittest.mock import patch

from postgrip.agent import Agent, workflow
from .test_python_sdk import FakeConnection


@workflow.defn(name="ExpiringWorkflow")
class ExpiringWorkflow:
    @workflow.run
    async def run(self, with_preparation=False, wait_for="timer"):
        workflow.set_handler(workflow.define_query("status"), lambda: True)
        try:
            if with_preparation:
                await workflow.execute_activity("prepare")
            if wait_for == "activity":
                await workflow.execute_activity("work")
            elif wait_for == "child":
                await workflow.execute_child("Child")
            else:
                await workflow.sleep(timedelta(days=1))
            return "expired"
        finally:
            if workflow.cancellation_requested():
                async def cleanup():
                    await workflow.execute_activity("cleanup")
                await workflow.CancellationScope.non_cancellable(cleanup)


def event(kind, task_id=None, **attributes):
    return {"type": kind, "task_id": task_id, "attributes": attributes}


def timer():
    return event("TimerStarted", "timer-1", duration_ms=86_400_000)


def cancel():
    return event("WorkflowCancellationRequested", reason="operator cancelled")


def task(args=None):
    return {"id": "workflow-task", "namespace": "default", "queue": "default", "type": "workflow:ExpiringWorkflow",
            "payload": {"workflowType": "ExpiringWorkflow", "workflowId": "workflow-1", "runId": "run-1", "args": args or []},
            "state": "leased", "lease_timeout_seconds": 30}


class CancellationReplayTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict("os.environ", {"POSTGRIP_AGENT_MANAGED_RUNTIME": "true"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def dispatch(self, connection, t=None):
        # New runtime instance and event loop on each durable redelivery.
        agent = Agent(connection=connection, task_queue="default", workflows=[ExpiringWorkflow], activities={})
        asyncio.run(agent._execute(t or task()))

    def test_cleanup_survives_suspension_and_restart(self):
        cases = {
            "activity": [event("ActivityTaskScheduled", "work-task", activity_type="work"), cancel()],
            "child": [event("ChildWorkflowExecutionStarted", "child-task", workflow_type="Child"), cancel()],
            "before timer": [cancel()],
            "pending timer": [timer(), cancel()],
            "fired before cancel": [timer(), event("TimerFired", "timer-1"), cancel()],
            "fired after cancel": [timer(), cancel(), event("TimerFired", "timer-1")],
            "after preparation": [event("ActivityTaskScheduled", "prepare-task", activity_type="prepare"), event("ActivityTaskCompleted", "prepare-task"), timer(), cancel()],
        }
        for name, history in cases.items():
            with self.subTest(case=name):
                c = FakeConnection()
                c.histories["run-1"] = history
                c.tasks["prepare-task"] = {"id": "prepare-task", "state": "succeeded", "result": {"value": None}}
                t = task([name == "after preparation", name if name in ("activity", "child") else "timer"])
                self.dispatch(c, t)
                self.assertEqual(c.failed, [])
                self.assertEqual(c.completed, [])
                self.assertEqual([x["type"] for x in c.enqueued], ["activity:cleanup"])
                self.assertEqual(len(c.blocked), 1)
                history.append(event("ActivityTaskScheduled", "task-1", activity_type="cleanup"))
                self.dispatch(c, t)
                self.assertEqual(c.failed, [])
                self.assertEqual(c.completed, [])
                self.assertEqual(len(c.enqueued), 1)
                self.assertEqual(len(c.blocked), 2)
                history.append(event("ActivityTaskCompleted", "task-1"))
                c.tasks["task-1"].update(state="succeeded", result={"value": None})
                self.dispatch(c, t)
                self.assertEqual(len(c.enqueued), 1)
                self.assertEqual(c.completed, [])
                self.assertEqual(len(c.failed), 1)
                self.assertEqual(c.failed[0][1], "operator cancelled")
                self.assertEqual(c.failed[0][2]["failure"]["type"], "CancelledFailure")

    def test_no_cleanup_on_ordinary_suspension_or_completion(self):
        c = FakeConnection()
        history = c.histories["run-1"] = []
        self.dispatch(c)
        self.assertEqual([x["type"] for x in c.enqueued], ["timer"])
        history.append(timer())
        self.dispatch(c)
        self.assertEqual(len(c.enqueued), 1)
        history.append(event("TimerFired", "timer-1"))
        self.dispatch(c)
        self.assertEqual(len(c.enqueued), 1)
        self.assertEqual(c.failed, [])
        self.assertEqual(c.completed[0][1]["value"], "expired")

    def test_cancellation_does_not_mask_divergence(self):
        c = FakeConnection()
        c.histories["run-1"] = [event("TimerStarted", "timer-1", duration_ms=1), cancel()]
        self.dispatch(c)
        self.assertEqual(c.enqueued, [])
        self.assertIn("timer command changed", c.failed[0][1])
        self.assertEqual(c.failed[0][2]["failure"]["type"], "WorkflowDeterminismViolation")

    def test_query_at_cancellation_boundary_is_read_only(self):
        c = FakeConnection()
        c.histories["run-1"] = [timer(), cancel()]
        c.workflows["run-1"] = {"task_id": "workflow-task", "queue": "default"}
        c.tasks["workflow-task"] = task()
        q = {**task(), "id": "query-task", "type": "query:ExpiringWorkflow", "payload": {
            "workflowId": "workflow-1", "workflowRunId": "run-1", "workflowType": "ExpiringWorkflow", "queryName": "status", "args": []}}
        self.dispatch(c, q)
        self.assertEqual(c.enqueued, [])
        self.assertEqual(c.failed, [])
        self.assertEqual(len(c.completed), 1)


class CancellationOwnerTests(unittest.TestCase):
    def test_completed_update_does_not_observe_later_cancellation(self):
        from postgrip.agent._replay import WorkflowReplay
        replay = WorkflowReplay([
            event("WorkflowUpdateAccepted", "update-1"),
            event("TimerStarted", "update-timer", duration_ms=10),
            event("WorkflowUpdateCompleted", "update-1"),
            timer(), cancel(), event("ActivityTaskScheduled", "cleanup-task", activity_type="cleanup"),
        ], {"update-timer": "update-1"})
        restore = replay.enter_owner("update-1", False)
        self.assertFalse(replay.is_cancellation_requested())
        replay.next_timer(10)
        self.assertFalse(replay.is_cancellation_requested())
        restore()
        self.assertFalse(replay.is_cancellation_requested())
        replay.next_timer(86_400_000)
        self.assertTrue(replay.is_cancellation_requested())
        replay.next_activity("cleanup")
        self.assertTrue(replay.is_cancellation_requested())
