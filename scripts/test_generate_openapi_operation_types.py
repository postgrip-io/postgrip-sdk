"""Operation annotation checks of the OpenAPI generator."""

from __future__ import annotations

import copy
import unittest
from typing import Any

from generate_openapi import IDEMPOTENCY_VALUES, operation_rows


def contract(idempotency: str, header: dict[str, Any] | None) -> dict[str, Any]:
    operation: dict[str, Any] = {
        "operationId": "sendThing",
        "x-postgrip-sdk-generate": True,
        "x-postgrip-auth-lane": "management",
        "x-postgrip-operation-class": "tenant-api",
        "x-postgrip-accepted-credentials": ["postgrip-token"],
        "x-postgrip-safety": "mutation",
        "x-postgrip-protocol": "http-json",
        "x-postgrip-idempotency": idempotency,
        "x-postgrip-pagination": "none",
        "x-postgrip-retry": "bounded",
        "responses": {"204": {"description": "sent"}},
    }
    if header is not None:
        operation["parameters"] = [{"$ref": "#/components/parameters/IdempotencyKey"}]
    return {
        "paths": {"/api/v1/things": {"post": operation}},
        "components": {"parameters": {"IdempotencyKey": header} if header is not None else {}},
    }


IDEMPOTENCY_KEY = {
    "name": "Idempotency-Key",
    "in": "header",
    "schema": {"type": "string", "minLength": 1, "maxLength": 128, "pattern": "^[!-~]+$"},
}


def header(required: bool) -> dict[str, Any]:
    return {**copy.deepcopy(IDEMPOTENCY_KEY), "required": required}


class IdempotencyAnnotationTests(unittest.TestCase):
    def test_matches_the_web_checker_values(self) -> None:
        self.assertEqual(IDEMPOTENCY_VALUES, ("none", "optional", "required"))

    def test_accepts_each_value_with_its_header(self) -> None:
        for idempotency, declared in (("none", None), ("optional", header(False)), ("required", header(True))):
            with self.subTest(idempotency):
                [row] = operation_rows(contract(idempotency, declared))
                self.assertEqual(row["idempotency"], idempotency)
                self.assertEqual(list(row["header_parameter_schemas"]), [] if declared is None else ["Idempotency-Key"])

    def test_rejects_an_unknown_value(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown x-postgrip-idempotency 'sometimes'"):
            operation_rows(contract("sometimes", header(False)))

    def test_rejects_an_annotation_out_of_step_with_its_header(self) -> None:
        for idempotency, declared, message in (
            ("none", header(False), "declares Idempotency-Key but x-postgrip-idempotency is none"),
            ("optional", None, "without an Idempotency-Key header"),
            ("required", None, "without an Idempotency-Key header"),
            ("optional", header(True), "must declare its Idempotency-Key header optional"),
            ("required", header(False), "must declare its Idempotency-Key header required"),
        ):
            with self.subTest(idempotency=idempotency, declared=declared):
                with self.assertRaisesRegex(ValueError, message):
                    operation_rows(contract(idempotency, declared))


if __name__ == "__main__":
    unittest.main()
