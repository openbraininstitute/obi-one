import logging
from collections import defaultdict
from typing import Any

from .validate_block import (
    openapi_schema,
    resolve_ref,
    validate_block,
    validate_hidden_refs_not_required,
    validate_string,
    validate_type,
)

L = logging.getLogger()


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


def validate_root_element(schema: dict, element: str, ref: str, config_ref: str) -> None:
    match ui_element := schema.get("ui_element"):
        case "root_block":
            validate_block(schema, ref)
        case "block_dictionary":
            validate_block_dictionary(schema, element, config_ref)
        case "block_single":
            validate_block_single(schema, element, config_ref)
        case _:
            msg = (
                f"Validation error at {config_ref} {element}: 'ui_element' must be 'root_block',"
                f" 'block_dictionary', or 'block_single'. Got: {ui_element}"
            )
            raise ValueError(msg)


def validate_dict(schema: dict, element: str, form_ref: str) -> None:
    if type(schema.get(element, {})) is not dict:
        msg = f"Validation error at {form_ref}: {element} must be a dictionary"
        raise ValueError(msg)


def validate_group_order(schema: dict, form_ref: str) -> None:  # noqa: C901
    groups: list[str] = validate_array(schema, "group_order", str, form_ref)

    used_groups: dict[str, list[int]] = defaultdict(list)

    for root_element, root_element_schema in schema.get("properties", {}).items():
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

    for block_schema in schema.get("additionalProperties", {}).get("oneOf"):
        ref = block_schema.get("$ref")

        if ref:
            block_schema = {**block_schema, **resolve_ref(openapi_schema, ref)}  # noqa: PLW2901

        validate_block(block_schema, ref)


def validate_block_single(schema: dict, key: str, config_ref: str) -> None:
    if schema.get("oneOf") is None:
        msg = f"Validation error at {config_ref}: block_single {key} must have 'oneOf'"
        raise ValueError(msg)

    for block_schema in schema.get("oneOf"):
        ref = block_schema.get("$ref")

        if ref:
            block_schema = {**block_schema, **resolve_ref(openapi_schema, ref)}  # noqa: PLW2901

        validate_block(block_schema, ref)


def validate_root_block(schema: dict, key: str, ref: str) -> None:
    if not isinstance(schema.get("properties"), dict):
        msg = f"Validation error at {ref}: root_block {key} must have 'properties'"
        raise TypeError(msg)

    validate_block(schema, ref)


def validate_config(form: dict, config_ref: str) -> None:
    if not form.get("ui_enabled"):
        L.info(f"Form {config_ref} is disabled, skipping validation.")
        return

    L.info(f"Validating form {config_ref} ...")

    validate_string(form, "title", config_ref)
    validate_string(form, "description", config_ref)
    validate_dict(form, "default_block_reference_labels", config_ref)
    validate_group_order(form, config_ref)
    validate_hidden_refs_not_required(form, config_ref)

    for root_element, root_element_schema in form.get("properties", {}).items():
        if root_element == "type":
            validate_type(root_element_schema, config_ref)
            continue

        ref = root_element_schema.get("$ref")

        if ref:
            root_element_schema = {  # noqa: PLW2901
                **root_element_schema,
                **resolve_ref(openapi_schema, ref),
            }

        validate_string(root_element_schema, "title", f"{root_element} at {config_ref}")
        validate_string(root_element_schema, "description", f"{root_element} at {config_ref}")

        validate_root_element(root_element_schema, root_element, ref, config_ref)


def test_schema() -> None:
    for path, value in openapi_schema["paths"].items():
        if not path.startswith("/generated"):
            continue

        schema_ref = value["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]

        schema = resolve_ref(openapi_schema, schema_ref)
        validate_config(schema, schema_ref)
