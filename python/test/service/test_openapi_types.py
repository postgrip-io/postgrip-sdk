from __future__ import annotations

from types import UnionType
from typing import Literal, get_args, get_origin, get_type_hints, is_typeddict
import unittest

from postgrip.service.openapi import (
    OpenAPIPostGripConfigurationWorkerSelector,
    OpenAPIServiceBuildLogMaintenanceResponse,
    OpenAPIServiceBuildLogSettingsMutationResponse,
    OpenAPIServiceBuildLogStatus,
    OpenAPIServiceRuntimeLogWorkerStatus,
    OperationId,
    OPENAPI_OPERATION_TYPES,
)
import postgrip.service as service

BUILD_LOG_SETTINGS = (
    {"projectId": str, "retentionDays": int, "updatedAt": str},
    {"lastTrimmedAt": str, "lastFlushedAt": str},
)
BUILD_LOG_STORAGE = (
    {"totalBytes": int, "deploymentsWithLogs": int},
    {"oldestEntry": str, "newestEntry": str},
)


class NestedServiceTypedDictTests(unittest.TestCase):
    """Closed inline contract objects resolve to TypedDicts at runtime."""

    def assert_typed_dict(
        self, value: object, required: dict[str, object], optional: dict[str, object] | None = None
    ) -> dict[str, object]:
        optional = optional or {}
        self.assertTrue(is_typeddict(value), f"{value!r} is not a TypedDict")
        self.assertEqual(value.__required_keys__, frozenset(required))
        self.assertEqual(value.__optional_keys__, frozenset(optional))
        hints = get_type_hints(value)
        self.assertEqual(set(hints), set(required) | set(optional))
        for name, expected in {**required, **optional}.items():
            if expected is not None:
                self.assertIs(hints[name], expected, name)
        return hints

    def test_build_log_status_nests_status_settings_storage_and_summary(self) -> None:
        hints = self.assert_typed_dict(
            OpenAPIServiceBuildLogStatus, {"status": None, "version": int, "etag": str}
        )
        status = self.assert_typed_dict(hints["status"], {"settings": None, "storage": None, "summary": None})
        self.assertEqual(hints["status"].__name__, "_SchemaServiceBuildLogStatusStatus")
        self.assertEqual(status["settings"].__name__, "_SchemaServiceBuildLogStatusStatusSettings")
        self.assert_typed_dict(status["settings"], *BUILD_LOG_SETTINGS)
        self.assert_typed_dict(status["storage"], *BUILD_LOG_STORAGE)
        self.assert_typed_dict(
            status["summary"], {"deploymentsLast24Hours": int, "activeBuilds": int, "failedDeployments": int}
        )

    def test_runtime_log_worker_status_nests_optional_settings_and_storage(self) -> None:
        hints = get_type_hints(OpenAPIServiceRuntimeLogWorkerStatus)
        self.assertIn("settings", OpenAPIServiceRuntimeLogWorkerStatus.__optional_keys__)
        self.assertIn("storage", OpenAPIServiceRuntimeLogWorkerStatus.__optional_keys__)
        self.assert_typed_dict(
            hints["settings"],
            {"enabled": bool, "retentionDays": int, "updatedAt": str},
            {"lastTrimmedAt": str, "lastFlushedAt": str},
        )
        self.assert_typed_dict(
            hints["storage"],
            {"databaseBytes": int, "containers": int, "logLines": int, "runningContainers": int},
            {"oldestEntry": str, "newestEntry": str},
        )

    def test_build_log_mutation_and_maintenance_responses_nest_results(self) -> None:
        settings = get_type_hints(OpenAPIServiceBuildLogSettingsMutationResponse)["settings"]
        self.assert_typed_dict(settings, *BUILD_LOG_SETTINGS)

        result = get_type_hints(OpenAPIServiceBuildLogMaintenanceResponse)["result"]
        result_hints = self.assert_typed_dict(
            result,
            {"deletedRows": int, "settings": None, "storage": None, "operation": None, "completedAt": str},
            {"retentionCutoff": str},
        )
        self.assertIs(get_origin(result_hints["operation"]), Literal)
        self.assertEqual(get_args(result_hints["operation"]), ("trim", "flush"))
        self.assert_typed_dict(result_hints["settings"], *BUILD_LOG_SETTINGS)
        self.assert_typed_dict(result_hints["storage"], *BUILD_LOG_STORAGE)

    def test_worker_selector_alternatives_are_typed_dicts(self) -> None:
        self.assertIs(get_origin(OpenAPIPostGripConfigurationWorkerSelector), UnionType)
        by_id, by_name = get_args(OpenAPIPostGripConfigurationWorkerSelector)
        self.assertEqual(by_id.__name__, "_SchemaPostGripConfigurationWorkerSelectorAlternative1")
        self.assert_typed_dict(by_id, {"id": str})
        self.assert_typed_dict(by_name, {"name": str})

    def test_nested_declarations_stay_out_of_public_aliases(self) -> None:
        from postgrip.service import openapi

        self.assertNotIn("OpenAPIServiceBuildLogStatusStatus", openapi.__all__)
        self.assertNotIn("_SchemaServiceBuildLogStatusStatus", openapi.__all__)
        self.assertFalse(hasattr(service, "OpenAPIServiceBuildLogStatusStatus"))
        self.assertEqual(
            OPENAPI_OPERATION_TYPES[OperationId.GET_SERVICE_BUILD_LOG_SETTINGS][1], OpenAPIServiceBuildLogStatus
        )


if __name__ == "__main__":
    unittest.main()
