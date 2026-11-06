"""Validator for the `task_result_selector` block UI element."""

from entitysdk.types import TaskResultType
from jsonschema import Draft7Validator, RefResolver, ValidationError

from obi_one.core.schema import SchemaKey

from .shared import openapi_schema


def validate_task_result_selector(schema: dict, param: str, ref: str) -> None:
    """Validate a TaskResult selector field.

    The field is a ``TaskResultFromID`` entity reference (an ``{"id_str": ...}`` object). It does
    not carry an ``entity_query`` (the frontend resolves the eligible results); instead it declares
    the concrete TaskResult subtype as data via ``task_result_type``, which the frontend uses to
    filter the selectable results.
    """
    task_result_type = schema.get(SchemaKey.TASK_RESULT_TYPE)
    valid_task_result_types = {member.value for member in TaskResultType}
    if task_result_type not in valid_task_result_types:
        msg = (
            f"Validation error at {ref}: task_result_selector param {param} must declare a "
            f"'{SchemaKey.TASK_RESULT_TYPE}' that is a valid TaskResultType. "
            f"Got: {task_result_type!r}"
        )
        raise ValidationError(msg) from None

    resolver = RefResolver.from_schema(openapi_schema)
    validator = Draft7Validator(schema, resolver=resolver)
    obj = {"id_str": "task_result_id"}
    try:
        validator.validate(obj)
    except ValidationError:
        msg = (
            f"Validation error at {ref}: task_result_selector param {param} failed to "
            f"validate an entity-reference object {obj}"
        )
        raise ValidationError(msg) from None
