from pathlib import Path
import json
import sys
import os
from fastapi.openapi.utils import get_openapi
from jsonschema import validate


current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
sys.path.append(str(parent_dir))

from app.application import app


def resolve_ref(openapi_schema: dict, ref: str) -> dict:
    """Resolves a JSON Reference (e.g., '#/components/schemas/Item')
    within the openapi_schema.
    """
    if not ref.startswith("#/"):
        msg = f"Only local references (starting with #/) are supported. Got: {ref}"
        raise ValueError(msg)

    # Split the path, skipping the first element which is '#'
    path_parts = ref.split("/")[1:]

    current_node = openapi_schema

    for part in path_parts:
        current_node = current_node.get(part)
        if current_node is None:
            msg = f"Reference '{ref}' could not be resolved. Part '{part}' missing."
            raise KeyError(msg)

    return current_node


def validate_all_properties_required(schema: dict) -> None:
    """Validates that all properties in a form schema are required."""
    print("Validating All Properties Required...")
    defined_props = set(schema.get("properties", {}).keys())
    required_props = set(schema.get("required", []))

    if defined_props == required_props:
        return
    if extra_in_props := defined_props - required_props:
        msg = f"Missing properties: {extra_in_props}"
        raise ValueError(msg)

    msg = f"Missing required properties: {required_props - defined_props}"
    raise ValueError(msg)


def validate_schema_groups(schema):
    """Validates that:
    1. The root 'group_order' list matches exactly the groups used in 'properties'.
    2. Within each group, the 'group_order' integers are unique.
    """
    print("Validating group name consistency...")
    defined_groups = set(schema.get("group_order", []))
    properties = schema.get("properties", {})
    used_groups = set()

    group_contents = {}

    for prop_name, prop_data in properties.items():
        g_name = prop_data.get("group")
        g_order = prop_data.get("group_order")

        if g_name:
            used_groups.add(g_name)

            if g_name not in group_contents:
                group_contents[g_name] = []
            group_contents[g_name].append((g_order, prop_name))

    # Are there groups defined in root but not used?
    extra_in_root = defined_groups - used_groups
    # Are there groups used in properties but missing from root?
    missing_in_root = used_groups - defined_groups

    if extra_in_root or missing_in_root:
        if extra_in_root:
            msg = f"Groups in root 'group_order' but NOT used in properties: {extra_in_root}"
            raise ValueError(msg)
        if missing_in_root:
            msg = f"Groups used in properties but NOT in root 'group_order': {missing_in_root}"
            raise ValueError(msg)

    # --- Check unique group_order within groups ---
    print("Checking Order Uniqueness...")

    for groups in group_contents.values():
        orders = [group[0] for group in groups]

        if len(orders) != len(set(orders)):
            seen = {}
            for order, name in groups:
                if order in seen:
                    msg = f"Conflict: '{name}' and '{seen[order]}' both have group_order: {order}"
                    raise ValueError(msg)
                seen[order] = name


def validate_block_schemas(schema: dict, openapi_schema: dict) -> None:
    """Validates block schemas."""
    print("Validating Block Schemas...")
    with Path.open(current_dir / "block_meta_schema.json") as f:
        block_meta_schema = json.load(f)

    properties = schema.get("properties", {})

    for key, block_schema in properties.items():
        print("Validating root element:", key)
        # root_block case
        if "$ref" in block_schema:
            schema = resolve_ref(openapi_schema, block_schema["$ref"])
            validate(schema, block_meta_schema)


def validate_schema() -> None:
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
    )

    for path, value in openapi_schema["paths"].items():
        if not path.startswith("/generated"):
            continue

        schema_ref = value["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]

        if schema_ref != "#/components/schemas/CircuitSimulationScanConfig":
            continue

        with Path.open(current_dir / "example_simulations_form.json") as f:
            example_simulations_form_schema = json.load(f)

        schema = resolve_ref(example_simulations_form_schema, schema_ref)

        with Path.open(current_dir / "meta_schema.json") as f:
            meta_schema = json.load(f)

        print("Validating schema at path:", path)
        validate(instance=schema, schema=meta_schema)
        validate_all_properties_required(schema)
        validate_schema_groups(schema)
        validate_block_schemas(schema, example_simulations_form_schema)


if __name__ == "__main__":
    validate_schema()
