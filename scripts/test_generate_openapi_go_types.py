"""Check that Go struct generation refuses mappings that lose an explicit null."""

from __future__ import annotations

import unittest

from generate_openapi import go_object_schema_source, go_struct_fields


class GoStructNullabilityTest(unittest.TestCase):
    def test_rejects_optional_nullable_properties(self) -> None:
        for name, property_schema in {
            "explicit type list": {"type": ["string", "null"]},
            "nullable keyword": {"type": "string", "nullable": True},
            "oneOf with null": {"oneOf": [{"type": "string"}, {"type": "null"}]},
            "JsonValue reference": {"$ref": "#/components/schemas/JsonValue"},
            "unconstrained schema": {},
        }.items():
            with self.subTest(name), self.assertRaises(SystemExit) as raised:
                go_object_schema_source("Fixture", {"type": "object", "properties": {"value": property_schema}})
            self.assertIn("optional nullable property 'value'", str(raised.exception))

    def test_allows_required_nullable_and_optional_non_nullable_properties(self) -> None:
        fields = go_struct_fields({
            "type": "object",
            "required": ["value"],
            "properties": {
                "value": {"oneOf": [{"type": "string"}, {"type": "null"}]},
                "name": {"type": "string"},
            },
        })
        self.assertIn('Value *string `json:"value"`', fields)
        self.assertIn('Name *string `json:"name,omitempty"`', fields)


if __name__ == "__main__":
    unittest.main()
