"""Check that generated Python TypedDicts preserve closed OpenAPI object shapes."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys
import types
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints, is_typeddict
import unittest

from generate_openapi import (
    ROOT,
    SPEC_PATHS,
    PythonDeclarations,
    merged_all_of_object_schema,
    python_closed_object_schema,
    python_schema_type,
    python_types_source,
    schema_ref_name,
    schema_required_alternatives,
)

PYTHON_SOURCE = ROOT / "python" / "src"
SCALAR_TYPES = {"boolean": bool, "integer": int, "number": float, "string": str}


def load_spec(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def closed_object_schemas(value: Any, path: str = "#") -> list[tuple[str, dict[str, Any]]]:
    """Return every closed object schema with properties anywhere in a contract."""
    found: list[tuple[str, dict[str, Any]]] = []
    if isinstance(value, dict):
        if python_closed_object_schema(value):
            found.append((path, value))
        for key, child in value.items():
            found.extend(closed_object_schemas(child, f"{path}/{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(closed_object_schemas(child, f"{path}/{index}"))
    return found


def union_members(hint: Any) -> tuple[Any, ...]:
    if get_origin(hint) in (Union, types.UnionType):
        return get_args(hint)
    return (hint,)


def compile_types(spec: dict[str, Any]) -> dict[str, Any]:
    source = (
        "from __future__ import annotations\n"
        "from typing import Any, Literal, TypeAlias, TypedDict\n\n"
        + python_types_source(spec, [])
    )
    namespace: dict[str, Any] = {"__name__": "generated_fixture"}
    exec(compile(source, "<generated>", "exec"), namespace)
    return namespace


class ContractShapeChecker:
    """Compare resolved generated annotations with the schemas they mirror."""

    def __init__(self, test: unittest.TestCase, globalns: dict[str, Any] | None = None):
        self.test = test
        self.globalns = globalns
        self.inline_closed_objects = 0

    def hints(self, typed_dict: Any) -> dict[str, Any]:
        return get_type_hints(typed_dict, globalns=self.globalns)

    def object(self, hint: Any, schema: dict[str, Any], path: str) -> None:
        alternatives = schema_required_alternatives(schema)
        base_required = set(schema.get("required", []))
        required_sets = [base_required | set(branch) for branch in alternatives] or [base_required]
        members = union_members(hint)
        self.test.assertEqual(len(members), len(required_sets), path)
        properties = schema.get("properties", {})
        for member, required in zip(members, required_sets):
            self.test.assertTrue(is_typeddict(member), f"{path} resolves to {member!r}, not a TypedDict")
            self.test.assertEqual(set(member.__required_keys__), required, f"{path} required keys")
            self.test.assertEqual(
                set(member.__optional_keys__), set(properties) - required, f"{path} optional keys"
            )
            member_hints = self.hints(member)
            self.test.assertEqual(set(member_hints), set(properties), f"{path} keys")
            for name, property_schema in properties.items():
                self.annotation(member_hints[name], property_schema, f"{path}.{name}")

    def annotation(self, hint: Any, schema: dict[str, Any], path: str) -> None:
        if not schema or schema_ref_name(schema):
            return
        if "const" in schema:
            self.test.assertEqual(get_args(hint), (schema["const"],), path)
            return
        if schema.get("enum"):
            self.test.assertIs(get_origin(hint), Literal, path)
            self.test.assertEqual(get_args(hint), tuple(schema["enum"]), path)
            return
        if python_closed_object_schema(schema):
            self.inline_closed_objects += 1
            self.object(hint, schema, path)
            return
        variants = schema.get("oneOf") or schema.get("anyOf")
        if variants:
            members = union_members(hint)
            if len(members) != len(variants):
                # A union collapses duplicate members; that only happens for unnamed, identical branches.
                self.test.assertFalse(any(python_closed_object_schema(variant) for variant in variants), path)
                return
            for index, (member, variant) in enumerate(zip(members, variants), 1):
                self.annotation(member, variant, f"{path}|{index}")
            return
        schema_type = schema.get("type")
        if schema_type == "array":
            self.test.assertIs(get_origin(hint), list, path)
            self.annotation(get_args(hint)[0], schema.get("items", {}), f"{path}[]")
            return
        if schema_type == "object" or "properties" in schema or "additionalProperties" in schema:
            additional = schema.get("additionalProperties")
            if isinstance(additional, dict):
                self.test.assertIs(get_origin(hint), dict, path)
                self.annotation(get_args(hint)[1], additional, f"{path}{{}}")
            else:
                self.test.assertEqual(hint, dict[str, Any], path)
            return
        if schema_type in SCALAR_TYPES and schema.get("format") != "binary":
            self.test.assertIs(hint, SCALAR_TYPES[schema_type], path)


class NestedTypedDictGenerationTests(unittest.TestCase):
    def fixture_spec(self, *extra: tuple[str, dict[str, Any]]) -> dict[str, Any]:
        closed_leaf = {
            "type": "object",
            "additionalProperties": False,
            "required": ["id"],
            "properties": {"id": {"type": "string"}, "note": {"type": "string"}},
        }
        parent = {
            "type": "object",
            "additionalProperties": False,
            "required": ["child"],
            "properties": {
                "child": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["count"],
                    "properties": {"count": {"type": "integer"}, "leaf": closed_leaf},
                },
                "rows": {"type": "array", "items": closed_leaf},
                "choice": {"oneOf": [closed_leaf, {"type": "null"}]},
                "labels": {"type": "object", "additionalProperties": {"type": "string"}},
                "open": {"type": "object", "properties": {"id": {"type": "string"}}},
                "anything": {"type": "object"},
            },
        }
        schemas = {"Parent": parent}
        schemas.update(dict(extra))
        return {"components": {"schemas": schemas}}

    def test_names_and_orders_nested_declarations(self) -> None:
        source = python_types_source(self.fixture_spec(), [])
        order = [
            "class _SchemaParentChildLeafOptional(TypedDict, total=False):",
            "class _SchemaParentChildLeaf(_SchemaParentChildLeafOptional):",
            "class _SchemaParentChildOptional(TypedDict, total=False):",
            "class _SchemaParentChild(_SchemaParentChildOptional):",
            "class _SchemaParentRowsItem(_SchemaParentRowsItemOptional):",
            "class _SchemaParentChoiceAlternative1(_SchemaParentChoiceAlternative1Optional):",
            "class _SchemaParent(_SchemaParentOptional):",
        ]
        positions = [source.index(line) for line in order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("    child: _SchemaParentChild\n", source)
        self.assertIn("    rows: list[_SchemaParentRowsItem]\n", source)
        self.assertIn("    choice: _SchemaParentChoiceAlternative1 | None\n", source)
        self.assertIn("    labels: dict[str, str]\n", source)
        self.assertIn("    open: dict[str, Any]\n", source)
        self.assertIn("    anything: dict[str, Any]", source)
        self.assertIn("OpenAPIParent: TypeAlias = _SchemaParent\n", source)
        self.assertNotIn("OpenAPIParentChild", source)

    def test_fixture_resolves_to_contract_shapes(self) -> None:
        spec = self.fixture_spec()
        namespace = compile_types(spec)
        checker = ContractShapeChecker(self, namespace)
        checker.object(namespace["OpenAPIParent"], spec["components"]["schemas"]["Parent"], "Parent")
        self.assertEqual(checker.inline_closed_objects, 4)

    def test_top_level_one_of_branches_are_alternatives(self) -> None:
        closed = {"type": "object", "additionalProperties": False, "required": ["id"], "properties": {"id": {"type": "string"}}}
        spec = {"components": {"schemas": {"Selector": {"oneOf": [closed, closed]}}}}
        source = python_types_source(spec, [])
        self.assertIn(
            "_SchemaSelector: TypeAlias = _SchemaSelectorAlternative1 | _SchemaSelectorAlternative2\n", source
        )
        self.assertLess(source.index("class _SchemaSelectorAlternative2(TypedDict):"), source.index("_SchemaSelector: TypeAlias"))

    def test_name_collision_fails_generation(self) -> None:
        colliding = {"type": "object", "required": ["other"], "properties": {"other": {"type": "string"}}}
        component_last = self.fixture_spec(("ParentChild", colliding))
        component_first = {
            "components": {"schemas": {"ParentChild": colliding, **self.fixture_spec()["components"]["schemas"]}}
        }
        for order, spec in (("component last", component_last), ("component first", component_first)):
            with self.subTest(order=order):
                with self.assertRaisesRegex(ValueError, "'_SchemaParentChild' collides"):
                    python_types_source(spec, [])

    def test_unnamed_closed_object_fails_generation(self) -> None:
        closed = {"type": "object", "additionalProperties": False, "properties": {"id": {"type": "string"}}}
        with self.assertRaisesRegex(ValueError, "no generated Python declaration name"):
            python_schema_type(closed)
        with self.assertRaisesRegex(ValueError, "no generated Python declaration name"):
            python_schema_type({"type": "object", "additionalProperties": closed}, "_SchemaMap", PythonDeclarations())


class ContractTypedDictTests(unittest.TestCase):
    """Walk the three mirrored contracts and their generated Python modules."""

    @classmethod
    def setUpClass(cls) -> None:
        if str(PYTHON_SOURCE) not in sys.path:
            sys.path.insert(0, str(PYTHON_SOURCE))

    def test_no_closed_object_maps_to_open_dictionary(self) -> None:
        for plane, spec_path in SPEC_PATHS.items():
            spec = load_spec(spec_path)
            for path, schema in closed_object_schemas(spec):
                with self.subTest(plane=plane, path=path):
                    annotation = python_schema_type(schema, "_SchemaProbe", PythonDeclarations())
                    self.assertEqual(annotation, "_SchemaProbe")
                    self.assertNotIn("dict[str, Any]", annotation)

    def test_generated_modules_match_contract_shapes(self) -> None:
        for plane, spec_path in SPEC_PATHS.items():
            spec = load_spec(spec_path)
            module = importlib.import_module(f"postgrip.{plane}.openapi")
            checker = ContractShapeChecker(self)
            component_inline = 0
            for name, raw_schema in spec["components"]["schemas"].items():
                schema = merged_all_of_object_schema(spec, raw_schema)
                hint = getattr(module, f"OpenAPI{name}")
                component_inline += len(closed_object_schemas(raw_schema)) - python_closed_object_schema(raw_schema)
                with self.subTest(plane=plane, schema=name):
                    if schema.get("type") == "object" or "properties" in schema:
                        checker.object(hint, schema, name)
                    else:
                        checker.annotation(hint, schema, name)
            with self.subTest(plane=plane):
                self.assertEqual(checker.inline_closed_objects, component_inline)
                # Operation-level inline closed objects have no naming rule; generation rejects them.
                self.assertEqual(closed_object_schemas(spec.get("paths", {})), [])


if __name__ == "__main__":
    unittest.main()
