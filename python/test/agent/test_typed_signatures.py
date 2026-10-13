"""Runtime checks of the Agent convenience annotations.

The repository runs no static type checker, so these tests resolve the
published hints with ``typing.get_type_hints`` and compare every ``**options``
TypedDict against the keywords its method forwards.
"""

import inspect
import unittest
from collections.abc import AsyncIterator, Iterator, Mapping
from datetime import timedelta
from typing import Any, Literal, Unpack, get_type_hints

from postgrip import agent
from postgrip.agent import client as client_module
from postgrip.agent import types
from postgrip.agent.client import (
    Client,
    Connection,
    ScheduleClient,
    TaskClient,
    WorkflowClient,
    WorkflowHandle,
    WorkflowUpdateHandle,
    _workflow_query_options,
)
from postgrip.agent.openapi import OpenAPIClient
from postgrip.agent.sandbox import SandboxClient


def _keys(typed_dict: type) -> set[str]:
    return set(typed_dict.__required_keys__) | set(typed_dict.__optional_keys__)


def _keyword_parameters(function: Any, *excluded: str) -> set[str]:
    return {
        name
        for name, parameter in inspect.signature(function).parameters.items()
        if name not in {"self", "cls", *excluded}
        and parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
    }


# (callable, {parameter or "return": expected hint}). Only the listed entries
# are compared; parameters such as identifiers keep their existing types.
EXPECTED_HINTS: list[tuple[Any, dict[str, Any]]] = [
    (Connection.health, {"return": types.HealthResponse}),
    (Connection.ready, {"return": types.ReadyResponse}),
    (Connection.list_namespaces, {"return": list[types.Namespace]}),
    (Connection.create_namespace, {"return": types.Namespace}),
    (Connection.enqueue_task, {"request": types.EnqueueTaskRequest, "return": types.Task}),
    (Connection.list_tasks, {"options": Unpack[types.ListTasksOptions], "return": list[types.Task]}),
    (Connection.get_task, {"return": types.Task}),
    (Connection.get_task_events_page, {"return": types.TaskEventPage}),
    (Connection.iter_task_events, {"return": Iterator[types.TaskEvent]}),
    (Connection.get_task_events, {"return": list[types.TaskEvent]}),
    (Connection.complete_task, {"result": types.TaskResult | Literal[client_module._Missing.MISSING], "return": types.Task}),
    (Connection.block_task, {"return": types.Task}),
    (Connection.fail_task, {"error": str | Literal[client_module._Missing.MISSING], "result": types.TaskResult | None, "return": types.Task}),
    (Connection.heartbeat_task, {"event": types.TaskEventInput | None, "return": types.Task}),
    (Connection.append_task_event, {"event": types.TaskEventInput | Literal[client_module._Missing.MISSING], "return": types.TaskEvent}),
    (Connection.poll_task_response, {"return": types.PollTaskResponse}),
    (Connection.poll_task, {"return": types.Task | None}),
    (Connection.get_workflow, {"return": types.WorkflowExecution}),
    (Connection.get_workflow_history_page, {"return": types.WorkflowHistoryPage}),
    (Connection.iter_workflow_history, {"return": Iterator[types.WorkflowHistoryEvent]}),
    (Connection.get_workflow_history, {"return": list[types.WorkflowHistoryEvent]}),
    (Connection.list_workflows, {"options": Unpack[types.ListWorkflowsOptions], "return": list[types.WorkflowExecution]}),
    (Connection.count_workflows, {"options": Unpack[types.CountWorkflowsOptions], "return": int}),
    (Connection.signal_workflow, {"args": list[Any] | None, "return": types.WorkflowHistoryEvent}),
    (
        Connection.signal_with_start_workflow,
        {"request": types.SignalWithStartWorkflowRequest, "return": types.SignalWithStartWorkflowResponse},
    ),
    (Connection.cancel_workflow, {"return": types.WorkflowHistoryEvent}),
    (Connection.terminate_workflow, {"return": types.WorkflowHistoryEvent}),
    (Connection.create_schedule, {"request": types.CreateScheduleRequest, "return": types.Schedule}),
    (Connection.list_schedules, {"options": Unpack[types.ListSchedulesOptions], "return": list[types.Schedule]}),
    (Connection.get_schedule, {"return": types.Schedule}),
    (Connection.update_schedule, {"request": types.UpdateScheduleRequest, "return": types.Schedule}),
    (Connection.delete_schedule, {"return": types.Schedule}),
    (Connection.pause_schedule, {"request": types.PauseScheduleRequest | None, "return": types.Schedule}),
    (Connection.unpause_schedule, {"request": types.UnpauseScheduleRequest | None, "return": types.Schedule}),
    (
        Connection.trigger_schedule,
        {"request": types.TriggerScheduleRequest | None, "return": types.TriggerScheduleResponse},
    ),
    (
        Connection.backfill_schedule,
        {"request": types.BackfillScheduleRequest, "return": types.BackfillScheduleResponse},
    ),
    (Connection.connect, {"options": Unpack[types.ConnectionOptions], "return": Connection}),
    (Client.connect, {"options": Unpack[types.ConnectionOptions], "return": Client}),
    (Client.start_workflow, {"options": Unpack[types.ClientStartWorkflowOptions], "return": WorkflowHandle}),
    (Client.execute_workflow, {"options": Unpack[types.ClientExecuteWorkflowOptions], "return": Any}),
    (WorkflowClient.start, {"args": list[Any] | None, "options": Unpack[types.WorkflowClientStartOptions], "return": WorkflowHandle}),
    (WorkflowClient.execute, {"options": Unpack[types.WorkflowClientExecuteOptions], "return": Any}),
    (
        WorkflowClient.signal_with_start,
        {"args": list[Any] | None, "options": Unpack[types.WorkflowClientStartOptions], "return": WorkflowHandle},
    ),
    (WorkflowClient.list, {"options": Unpack[types.WorkflowListOptions], "return": list[types.WorkflowExecution]}),
    (WorkflowClient.count, {"options": Unpack[types.WorkflowCountOptions], "return": int}),
    (WorkflowHandle.describe, {"return": types.WorkflowExecution}),
    (WorkflowHandle.describe_sync, {"return": types.WorkflowExecution}),
    (WorkflowHandle.history, {"return": list[types.WorkflowHistoryEvent]}),
    (WorkflowHandle.history_sync, {"return": list[types.WorkflowHistoryEvent]}),
    (WorkflowHandle.events, {"return": list[types.TaskEvent]}),
    (WorkflowHandle.watch_events, {"return": AsyncIterator[types.TaskEvent]}),
    (WorkflowUpdateHandle.events, {"return": list[types.TaskEvent]}),
    (WorkflowUpdateHandle.watch_events, {"return": AsyncIterator[types.TaskEvent]}),
    (TaskClient.enqueue, {"payload": types.JsonValue, "return": types.Task}),
    (TaskClient.shell_exec, {"return": types.Task}),
    (TaskClient.container_exec, {"return": types.Task}),
    (TaskClient.workflow_runtime, {"return": types.Task}),
    (TaskClient.noop, {"return": types.Task}),
    (TaskClient.events, {"return": list[types.TaskEvent]}),
    (TaskClient.watch_events, {"return": AsyncIterator[types.TaskEvent]}),
    (ScheduleClient.create, {"request": types.CreateScheduleRequest, "return": types.Schedule}),
    (
        ScheduleClient.create_workflow_schedule,
        {
            "args": list[Any] | None,
            "calendar": types.ScheduleCalendarSpec | None,
            "missed_run_policy": types.ScheduleMissedRunPolicy | None,
            "workflow_id_reuse_policy": types.WorkflowIdReusePolicy | None,
            "overlap_policy": types.ScheduleOverlapPolicy | None,
            "retry": types.RetryPolicy | None,
            "memo": dict[str, types.JsonValue] | None,
            "search_attributes": dict[str, types.JsonValue] | None,
            "ui": types.WorkflowUIMetadata | None,
            "return": types.Schedule,
        },
    ),
    (ScheduleClient.list, {"options": Unpack[types.ListSchedulesOptions], "return": list[types.Schedule]}),
    (ScheduleClient.get, {"return": types.Schedule}),
    (ScheduleClient.update, {"request": types.UpdateScheduleRequest, "return": types.Schedule}),
    (ScheduleClient.delete, {"return": types.Schedule}),
    (ScheduleClient.pause, {"request": types.PauseScheduleRequest | None, "return": types.Schedule}),
    (ScheduleClient.unpause, {"request": types.UnpauseScheduleRequest | None, "return": types.Schedule}),
    (ScheduleClient.trigger, {"request": types.TriggerScheduleRequest | None, "return": types.TriggerScheduleResponse}),
    (ScheduleClient.backfill, {"request": types.BackfillScheduleRequest, "return": types.BackfillScheduleResponse}),
    (SandboxClient.create, {"request": types.SandboxCreateRequest, "return": types.Sandbox}),
    (SandboxClient.list, {"return": list[types.Sandbox]}),
    (SandboxClient.get, {"return": types.Sandbox}),
    (SandboxClient.start, {"return": types.Sandbox}),
    (SandboxClient.stop, {"return": types.Sandbox}),
    (SandboxClient.delete, {"return": types.Sandbox}),
    (SandboxClient.create_session, {"return": types.CreateSandboxSessionResponse}),
    (SandboxClient.upload_workspace, {"return": types.SandboxWorkspace}),
    (SandboxClient.list_workspaces, {"return": list[types.SandboxWorkspace]}),
    (SandboxClient.get_workspace, {"return": types.SandboxWorkspace}),
    (SandboxClient.wait_until_running, {"return": types.Sandbox}),
]


class _RecordingConnection:
    """Captures the enqueue request ``WorkflowClient.start`` builds."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def enqueue_task(self, request: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(request)
        return {"id": "task-1", "payload": {}}


class TypedAgentSignatureTests(unittest.TestCase):
    def test_convenience_hints_resolve_to_contract_aliases(self) -> None:
        for function, expected in EXPECTED_HINTS:
            with self.subTest(function=function.__qualname__):
                hints = get_type_hints(function)
                for name, hint in expected.items():
                    self.assertEqual(hints[name], hint, f"{function.__qualname__}: {name}")

    def test_every_public_convenience_method_resolves_its_hints(self) -> None:
        for cls in (
            Connection,
            Client,
            WorkflowClient,
            WorkflowHandle,
            WorkflowUpdateHandle,
            TaskClient,
            ScheduleClient,
            SandboxClient,
        ):
            for name, member in vars(cls).items():
                if name.startswith("_"):
                    continue
                function = member.__func__ if isinstance(member, classmethod) else member
                if not inspect.isfunction(function):
                    continue
                with self.subTest(method=f"{cls.__name__}.{name}"):
                    hints = get_type_hints(function)
                    for hint_name, hint in hints.items():
                        self.assertNotEqual(hint, dict[str, Any], f"{cls.__name__}.{name}: {hint_name}")
                        self.assertNotEqual(hint, list[dict[str, Any]], f"{cls.__name__}.{name}: {hint_name}")

    def test_async_wrappers_mirror_sync_annotations(self) -> None:
        for async_method, sync_method in (
            (WorkflowHandle.describe, WorkflowHandle.describe_sync),
            (WorkflowHandle.history, WorkflowHandle.history_sync),
            (WorkflowHandle.events, TaskClient.events),
            (WorkflowUpdateHandle.events, TaskClient.events),
        ):
            with self.subTest(method=async_method.__qualname__):
                self.assertEqual(get_type_hints(async_method)["return"], get_type_hints(sync_method)["return"])

    def test_connection_options_match_connection_constructor(self) -> None:
        self.assertEqual(
            _keys(types.ConnectionOptions),
            _keyword_parameters(Connection.__init__, "address"),
        )

    def test_list_tasks_and_schedules_options_match_generated_queries(self) -> None:
        self.assertEqual(_keys(types.ListTasksOptions), _keyword_parameters(OpenAPIClient.list_tasks))
        self.assertEqual(_keys(types.ListSchedulesOptions), _keyword_parameters(OpenAPIClient.list_schedules))

    def test_workflow_query_options_match_generated_queries(self) -> None:
        # `search` is built from `search_attributes`; passing it directly would
        # collide with the keyword the method supplies.
        self.assertEqual(
            _keys(types.CountWorkflowsOptions),
            _keyword_parameters(OpenAPIClient.count_workflows, "search") | {"search_attributes"},
        )
        self.assertEqual(
            _keys(types.ListWorkflowsOptions),
            _keyword_parameters(OpenAPIClient.list_workflows, "search") | {"search_attributes"},
        )

    def test_workflow_client_query_options_add_only_mapped_aliases(self) -> None:
        aliases = {"workflow_id", "workflow_type", "task_queue"}
        self.assertEqual(_keys(types.WorkflowListOptions), _keys(types.ListWorkflowsOptions) | aliases)
        self.assertEqual(_keys(types.WorkflowCountOptions), _keys(types.CountWorkflowsOptions) | aliases)
        for typed_dict, target in (
            (types.WorkflowListOptions, types.ListWorkflowsOptions),
            (types.WorkflowCountOptions, types.CountWorkflowsOptions),
        ):
            for key in _keys(typed_dict):
                with self.subTest(options=typed_dict.__name__, key=key):
                    mapped = _workflow_query_options({key: "value"})
                    self.assertLessEqual(set(mapped), _keys(target))

    def test_workflow_client_start_options_are_exactly_the_forwarded_extras(self) -> None:
        self.assertEqual(
            _keys(types.WorkflowClientStartOptions),
            {
                "workflow_id_reuse_policy",
                "workflow_run_timeout",
                "workflow_run_timeout_ms",
                "lease_timeout_seconds",
                "retry",
                "memo",
                "search_attributes",
                "ui",
            },
        )
        values: dict[str, Any] = {
            "workflow_id_reuse_policy": "reject_duplicate",
            "workflow_run_timeout": timedelta(seconds=2),
            "workflow_run_timeout_ms": 3000,
            "lease_timeout_seconds": 30,
            "retry": {"maximumAttempts": 2},
            "memo": {"owner": "docs"},
            "search_attributes": {"customer": "cust-1"},
            "ui": {"displayName": "Example"},
        }
        self.assertEqual(set(values), _keys(types.WorkflowClientStartOptions))

        def enqueued(**options: Any) -> dict[str, Any]:
            connection = _RecordingConnection()
            WorkflowClient(connection).start("Example", workflow_id="workflow-1", **options)  # type: ignore[arg-type]
            return connection.requests[0]

        baseline = enqueued()
        for key, value in values.items():
            with self.subTest(key=key):
                self.assertNotEqual(enqueued(**{key: value}), baseline)

    def test_execute_and_client_start_options_extend_start_options(self) -> None:
        start_named = _keyword_parameters(WorkflowClient.start, "workflow")
        self.assertEqual(start_named, {"workflow_id", "task_queue", "namespace", "args"})
        start_extras = _keys(types.WorkflowClientStartOptions)
        self.assertEqual(
            _keys(types.WorkflowClientExecuteOptions),
            start_named | start_extras | {"timeout"},
        )
        # Positional workflow arguments become `args`, so the Client form
        # cannot also take them as a keyword; `id` aliases `workflow_id`.
        self.assertEqual(
            _keys(types.ClientStartWorkflowOptions),
            (start_named - {"args"}) | start_extras | {"id"},
        )
        self.assertEqual(
            _keys(types.ClientExecuteWorkflowOptions),
            _keys(types.ClientStartWorkflowOptions) | {"timeout"},
        )

    def test_option_typed_dicts_are_optional_and_exported(self) -> None:
        for name in (
            "ClientExecuteWorkflowOptions",
            "ClientStartWorkflowOptions",
            "ConnectionOptions",
            "CountWorkflowsOptions",
            "ListSchedulesOptions",
            "ListTasksOptions",
            "ListWorkflowsOptions",
            "WorkflowClientExecuteOptions",
            "WorkflowClientStartOptions",
            "WorkflowCountOptions",
            "WorkflowListOptions",
        ):
            with self.subTest(name=name):
                typed_dict = getattr(types, name)
                self.assertEqual(typed_dict.__required_keys__, frozenset())
                self.assertIs(getattr(agent, name), typed_dict)
                self.assertIn(name, agent.__all__)
                # Every field hint resolves at runtime.
                get_type_hints(typed_dict)

    def test_user_data_stays_open(self) -> None:
        start = get_type_hints(types.WorkflowClientStartOptions)
        self.assertEqual(start["memo"], dict[str, types.JsonValue] | None)
        self.assertEqual(start["search_attributes"], dict[str, types.JsonValue] | None)
        self.assertEqual(get_type_hints(types.WorkflowClientExecuteOptions)["args"], list[Any] | None)
        self.assertEqual(
            get_type_hints(types.CountWorkflowsOptions)["search_attributes"],
            Mapping[str, types.JsonValue] | None,
        )


if __name__ == "__main__":
    unittest.main()
