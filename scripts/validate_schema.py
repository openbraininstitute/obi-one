import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from fastapi.openapi.utils import get_openapi


current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
sys.path.append(str(parent_dir))

from app.application import app  # noqa: E402
from app.logger import L  # noqa: E402

openapi_schema = get_openapi(
    title=app.title,
    version=app.version,
    openapi_version=app.openapi_version,
    description=app.description,
    routes=app.routes,
)


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


def validate_hidden_refs_not_required(schema: dict, ref: str) -> None:
    for key, param_schema in schema["properties"].items():
        if param_schema.get("ui_hidden") and key in schema.get("required", []):
            msg = (
                f"The hidden reference {key} is marked as required in the schema"
                f" but shouldn't be\n\n In {ref}"
            )
            raise ValueError(msg)


def validate_string(schema: dict, prop: str, ref: str) -> None:
    value = schema.get(prop)

    if type(value) is not str:
        msg = f"Validation error at {ref}: {prop} must be a string. Got: {type(value)}"
        raise ValueError(msg)


def validate_array(schema: dict, prop: str, array_type: type, ref: str) -> list[Any]:
    value = schema.get(prop, [])
    for item in value:  # type:ignore reportOptionalIterable
        if type(item) is not array_type:
            msg = (
                f"Validation error at {ref}: Array items must be of type {array_type}."
                f"Got: {type(item)}"
            )
            raise ValueError(msg)

    return value


def validate_root_element(schema: dict, element: str, form_ref: str) -> None:
    if schema.get("ui_element") not in {"root_block", "block_dictionary"}:
        msg = (
            f"Validation error at {form_ref} {element}: 'ui_element' must be 'root_block' or"
            f"'block_dictionary'. Got: {schema.get('ui_element')}"
        )
        raise ValueError(msg)

    validate_string(schema, "title", f"{element} in {form_ref}")
    validate_string(schema, "description", f"{element} in {form_ref}")

    if schema["ui_element"] == "block_dictionary":
        validate_block_dictionary(schema, element, form_ref)

    if schema["ui_element"] == "root_block":
        validate_root_block(schema, element, form_ref)


def validate_type(schema: dict, form_ref: str) -> None:
    if not isinstance(schema, dict):
        msg = f"Validation error at {form_ref}: 'type' schema must be a dictionary"
        raise TypeError(msg)

    if not schema.get("default"):
        msg = f"Validation error at {form_ref}: 'type' must have a default"
        raise ValueError(msg)


def validate_dict(schema: dict, element: str, form_ref: str) -> None:
    if type(schema.get(element, {})) is not dict:
        msg = f"Validation error at {form_ref}: {element} must be a dictionary"
        raise ValueError(msg)


def validate_group_order(schema: dict, form_ref: str) -> None:  # noqa: C901
    groups: list[str] = validate_array(schema, "group_order", str, form_ref)

    used_groups: dict[str, list[int]] = defaultdict(list)

    for root_element, root_element_schema in schema.get("properties", {}).items():  # type:ignore[]
        if root_element == "type":
            continue

        group = root_element_schema.get("group")
        group_order = root_element_schema.get("group_order")
        if not group:
            msg = f"Validation error at {form_ref}: {root_element} must have a group"
            raise ValueError(msg)

        if group_order is None:
            msg = f"Validation error at {form_ref}: {root_element} must have a group_order"
            raise ValueError(msg)

        if not isinstance(group_order, int):
            msg = f"Validation error at {form_ref}: {root_element} group_order must be an integer"
            raise TypeError(msg)

        if not isinstance(group, str):
            msg = f"Validation error at {form_ref}: {root_element} group must be a string"
            raise TypeError(msg)

        if group not in groups:
            msg = (
                f"Validation error at {form_ref}: {root_element} has group '{group}'"
                "not in root group_order"
            )
            raise ValueError(msg)

        used_groups[group].append(group_order)

    if extra_groups := (set(groups) - set(used_groups.keys())):
        msg = (
            f"Validation error at {form_ref}: group_order contains groups not used in properties"
            f" {extra_groups}"
        )

        raise ValueError(msg)

    for used_group, used_group_orders in used_groups.items():
        if len(used_group_orders) != len(set(used_group_orders)):
            msg = (
                f"Validation error at {form_ref}: group '{used_group}' has duplicate group_order"
                f" values: {used_group_orders}"
            )
            raise ValueError(msg)


def validate_block_dictionary(schema: dict, key: str, config_ref: str) -> None:
    if schema.get("additionalProperties", {}).get("oneOf") is None:
        msg = (
            f"Validation error at {config_ref}: block_dictionary {key} must have 'oneOf'"
            "in additionalProperties"
        )
        raise ValueError(msg)


def validate_root_block(schema: dict, key: str, config_ref: str) -> None:
    if not isinstance(schema.get("properties"), dict):
        msg = f"Validation error at {config_ref}: root_block {key} must have 'properties'"
        raise TypeError(msg)


def validate_config(form: dict, ref: str) -> None:
    if not form.get("ui_enabled"):
        L.info(f"Form {ref} is disabled, skipping validation.")
        return

    L.info(f"Validating form {ref} ...")

    validate_string(form, "title", ref)
    validate_string(form, "description", ref)
    validate_dict(form, "default_block_reference_labels", ref)
    validate_group_order(form, ref)
    validate_hidden_refs_not_required(form, ref)

    for root_element, root_element_schema in form.get("properties", {}).items():  # type:ignore[]
        if root_element == "type":
            validate_type(root_element_schema, ref)
            continue

        if root_element_schema.get("$ref"):
            root_element_schema = {  # noqa: PLW2901
                **root_element_schema,
                **resolve_ref(openapi_schema, root_element_schema["$ref"]),
            }

        validate_root_element(root_element_schema, root_element, ref)


def validate_schema() -> None:
    for path, value in openapi_schema["paths"].items():
        if not path.startswith("/generated"):
            continue

        schema_ref = value["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]

        schema = resolve_ref(openapi_schema, schema_ref)
        validate_config(schema, schema_ref)


if __name__ == "__main__":
    validate_schema()
