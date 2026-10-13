from __future__ import annotations

import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Event, Lock, Thread
from typing import Any, Iterator
import unittest
from urllib.parse import urlsplit

from postgrip.agent import Client, Connection, TaskFailedError, TimeoutFailure, WorkflowHandle

HOLD = object()
# A held request ends on its own if the client never disconnects, so a
# regression fails the test instead of hanging it.
_HOLD_SECONDS = 3


class _AgentServer:
    """Local Agent server that answers or holds each request by path."""

    def __init__(self, routes: dict[str, list[Any]]):
        self.routes = routes
        self.paths: list[str] = []
        self.held = Event()
        self.disconnected = Event()
        self._lock = Lock()

    def handle(self, handler: BaseHTTPRequestHandler) -> None:
        path = urlsplit(handler.path).path
        with self._lock:
            self.paths.append(path)
            queue = self.routes.get(path) or [{"error": "unexpected request"}]
            action = queue.pop(0) if len(queue) > 1 else queue[0]
        if action is HOLD:
            self._hold(handler)
            return
        status = 404 if "error" in action else 200
        body = json.dumps(action).encode()
        handler.send_response(status)
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def _hold(self, handler: BaseHTTPRequestHandler) -> None:
        self.held.set()
        handler.connection.settimeout(_HOLD_SECONDS)
        try:
            if handler.connection.recv(1) == b"":
                self.disconnected.set()
        except TimeoutError:
            handler.send_error(500, "held request was never cancelled")
        except OSError:
            self.disconnected.set()


@contextmanager
def serve(routes: dict[str, list[Any]]) -> Iterator[tuple[_AgentServer, Connection]]:
    state = _AgentServer(routes)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            state.handle(self)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield state, Connection(f"http://{host}:{port}", insecure_development=True)
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


async def _wait(event: Event) -> bool:
    return await asyncio.to_thread(event.wait, 2)


class RequestCancellationTests(unittest.TestCase):
    def _assert_cancel_closes_held_request(
        self,
        routes: dict[str, list[Any]],
        start: Any,
        expected_paths: list[str],
    ) -> None:
        with serve(routes) as (server, connection):
            async def run() -> None:
                task = asyncio.create_task(start(connection))
                self.assertTrue(await _wait(server.held), "request was not held")
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertTrue(await _wait(server.disconnected), "held connection remained open")

            # asyncio.run joins the default executor, so the cancelled request
            # thread has finished before the request log is checked.
            asyncio.run(run())
            self.assertEqual(server.paths, expected_paths)

    def _result_routes(self) -> dict[str, list[Any]]:
        return {"/api/v1/tasks/task-1": [{"id": "task-1", "state": "running"}, HOLD]}

    def test_cancelling_result_closes_held_task_request(self) -> None:
        self._assert_cancel_closes_held_request(
            self._result_routes(),
            lambda connection: WorkflowHandle(connection, "workflow-1", task_id="task-1").result(
                timeout=30,
                poll_interval=0.01,
            ),
            ["/api/v1/tasks/task-1", "/api/v1/tasks/task-1"],
        )

    def test_cancelling_result_without_timeout_closes_held_task_request(self) -> None:
        self._assert_cancel_closes_held_request(
            self._result_routes(),
            lambda connection: WorkflowHandle(connection, "workflow-1", task_id="task-1").result(
                poll_interval=0.01,
            ),
            ["/api/v1/tasks/task-1", "/api/v1/tasks/task-1"],
        )

    def test_cancelling_history_closes_held_request(self) -> None:
        self._assert_cancel_closes_held_request(
            {"/api/v1/workflows/workflow-1/history": [HOLD]},
            lambda connection: WorkflowHandle(connection, "workflow-1").history(),
            ["/api/v1/workflows/workflow-1/history"],
        )

    def test_cancelling_events_task_lookup_closes_held_request(self) -> None:
        self._assert_cancel_closes_held_request(
            {"/api/v1/workflows/workflow-1": [HOLD]},
            lambda connection: Client(connection).get_workflow_handle("workflow-1").events(),
            ["/api/v1/workflows/workflow-1"],
        )

    def test_cancelling_watch_events_task_lookup_closes_held_request(self) -> None:
        async def first_event(connection: Connection) -> Any:
            return await anext(Client(connection).get_workflow_handle("workflow-1").watch_events())

        self._assert_cancel_closes_held_request(
            {"/api/v1/workflows/workflow-1": [HOLD]},
            first_event,
            ["/api/v1/workflows/workflow-1"],
        )

    def test_cancelling_watch_events_closes_held_task_request(self) -> None:
        async def drain(connection: Connection) -> None:
            async for _event in WorkflowHandle(connection, "workflow-1", task_id="task-1").watch_events(
                poll_interval=0.01,
            ):
                pass

        self._assert_cancel_closes_held_request(
            {
                "/api/v1/tasks/task-1/events": [{"items": []}],
                "/api/v1/tasks/task-1": [HOLD],
            },
            drain,
            ["/api/v1/tasks/task-1/events", "/api/v1/tasks/task-1"],
        )

    def test_async_requests_keep_redirect_policy(self) -> None:
        target_routes = {"/api/v1/workflows/workflow-1": [{"id": "workflow-1", "type": "Example", "task_id": "task-9"}]}
        with serve(target_routes) as (target, target_connection):
            target_url = target_connection.address

            class RedirectHandler(BaseHTTPRequestHandler):
                def do_GET(self) -> None:
                    path = urlsplit(self.path).path
                    if path == "/api/v1/workflows/same-origin":
                        location = "/api/v1/workflows/workflow-1"
                    elif path == "/api/v1/workflows/cross-origin":
                        location = target_url + "/api/v1/workflows/workflow-1"
                    else:
                        body = b'{"id":"workflow-1","type":"Example","task_id":"task-1"}'
                        self.send_response(200)
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                        return
                    self.send_response(302)
                    self.send_header("Location", location)
                    self.end_headers()

                def log_message(self, _format: str, *_args: object) -> None:
                    return

            server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                connection = Connection(f"http://{host}:{port}", insecure_development=True)

                async def run() -> None:
                    workflow = await WorkflowHandle(connection, "same-origin").describe()
                    self.assertEqual(workflow["task_id"], "task-1")
                    with self.assertRaises(RuntimeError):
                        await WorkflowHandle(connection, "cross-origin").describe()

                asyncio.run(run())
            finally:
                server.shutdown()
                thread.join()
                server.server_close()

        self.assertEqual(target.paths, [])


class _ScriptedConnection(Connection):
    def __init__(self, tasks: dict[str, list[dict[str, Any]]], workflow: dict[str, Any] | None = None):
        super().__init__("http://agent.test", insecure_development=True)
        self.tasks = tasks
        self.workflow = workflow
        self.reads: list[str] = []

    def get_task(self, task_id: str) -> dict[str, Any]:
        self.reads.append(task_id)
        queue = self.tasks[task_id]
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def get_workflow(self, workflow_id_or_run_id: str) -> dict[str, Any]:
        self.reads.append(f"workflow:{workflow_id_or_run_id}")
        assert self.workflow is not None
        return self.workflow


class WorkflowResultTests(unittest.TestCase):
    """result() and result_sync() share one decision path."""

    def _results(self, make_connection: Any) -> list[tuple[Any, list[str], str | None]]:
        outcomes = []
        for wait in ("sync", "async"):
            connection = make_connection()
            handle = WorkflowHandle(connection, "workflow-1", task_id="task-1")
            if wait == "sync":
                value = handle.result_sync(poll_interval=0)
            else:
                value = asyncio.run(handle.result(poll_interval=0))
            outcomes.append((value, connection.reads, handle.task_id))
        return outcomes

    def test_follows_continue_as_new_and_returns_value(self) -> None:
        def make_connection() -> _ScriptedConnection:
            return _ScriptedConnection({
                "task-1": [{"id": "task-1", "state": "succeeded", "result": {"continue_as_new": {"task_id": "task-2"}}}],
                "task-2": [
                    {"id": "task-2", "state": "running"},
                    {"id": "task-2", "state": "succeeded", "result": {"value": "done"}},
                ],
            })

        for outcome in self._results(make_connection):
            self.assertEqual(outcome, ("done", ["task-1", "task-2", "task-2"], "task-2"))

    def test_re_resolves_failed_task_to_current_run(self) -> None:
        def make_connection() -> _ScriptedConnection:
            return _ScriptedConnection(
                {
                    "task-1": [{"id": "task-1", "state": "failed", "error": "retrying"}],
                    "task-2": [{"id": "task-2", "state": "succeeded", "result": {"value": 7}}],
                },
                {"id": "workflow-1", "state": "running", "task_id": "task-2"},
            )

        for outcome in self._results(make_connection):
            self.assertEqual(outcome, (7, ["task-1", "workflow:workflow-1", "task-2"], "task-2"))

    def test_raises_task_failure_when_workflow_has_no_new_run(self) -> None:
        for wait in ("sync", "async"):
            connection = _ScriptedConnection(
                {"task-1": [{"id": "task-1", "state": "failed", "error": "boom"}]},
                {"id": "workflow-1", "state": "failed", "task_id": "task-1"},
            )
            handle = WorkflowHandle(connection, "workflow-1", task_id="task-1")
            with self.subTest(wait=wait), self.assertRaisesRegex(TaskFailedError, "boom"):
                if wait == "sync":
                    handle.result_sync(poll_interval=0)
                else:
                    asyncio.run(handle.result(poll_interval=0))

    def test_raises_timeout_while_task_is_running(self) -> None:
        for wait in ("sync", "async"):
            connection = _ScriptedConnection({"task-1": [{"id": "task-1", "state": "running"}]})
            handle = WorkflowHandle(connection, "workflow-1", task_id="task-1")
            with self.subTest(wait=wait), self.assertRaises(TimeoutFailure):
                if wait == "sync":
                    handle.result_sync(timeout=0.02, poll_interval=0.005)
                else:
                    asyncio.run(handle.result(timeout=0.02, poll_interval=0.005))


if __name__ == "__main__":
    unittest.main()
