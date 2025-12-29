import sys
from pathlib import Path

from fastapi.openapi.utils import get_openapi
from jsonschema import ValidationError, validate


current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
sys.path.append(str(parent_dir))

from app.application import app  # noqa: E402

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


def validate_type(schema: dict, ref: str) -> None:
    if not isinstance(schema, dict):
        msg = f"Validation error at {ref}: 'type' schema must be a dictionary"
        raise TypeError(msg)

    if not schema.get("default"):
        msg = f"Validation error at {ref}: 'type' must have a default"
        raise ValueError(msg)


def validate_string_param(schema: dict, param: str, ref: str) -> None:
    try:
        validate("a", schema)

    except ValidationError:
        msg = f"Validation error at {ref}: string_input param {param} failedto validate a string"
        raise ValidationError(msg) from None


def validate_float_param_sweep(schema: dict, param: str, ref: str) -> None:
    if schema.get("anyOf", [{}])[0].get("type") != "number":
        msg = (
            f"Validation error at {ref}: float_parameter_sweep param {param} should"
            "be a union with a 'number' as first element"
        )
        raise ValidationError(msg) from None

    try:
        validate(1.0, schema)

    except ValidationError:
        msg = (
            f"Validation error at {ref}: float_parameter_sweep param {param} failed"
            "to validate an float"
        )
        raise ValidationError(msg) from None

    try:
        validate([1.0], schema)

    except ValidationError:
        msg = (
            f"Validation error at {ref}: float_parameter_sweep param {param} failed"
            "to validate an float array"
        )
        raise ValidationError(msg) from None


def validate_int_param_sweep(schema: dict, param: str, ref: str) -> None:
    if schema.get("anyOf", [{}])[0].get("type") != "integer":
        msg = (
            f"Validation error at {ref}: int_parameter_sweep param {param} should"
            "be a union with an 'int' as first element"
        )
        raise ValidationError(msg) from None
    try:
        validate(1, schema)

    except ValidationError:
        msg = (
            f"Validation error at {ref}: int_parameter_sweep param {param} failedto validate an int"
        )
        raise ValidationError(msg) from None

    try:
        validate([1], schema)

    except ValidationError:
        msg = (
            f"Validation error at {ref}: int_parameter_sweep param {param} failed"
            "to validate an int array"
        )
        raise ValidationError(msg) from None


def validate_entity_property_dropdown(schema: dict, param: str, ref: str) -> None:
    validate_string(schema, "entity_type", f"{param} at {ref}")
    validate_string(schema, "property", f"{param} at {ref}")

    try:
        validate_string_param(schema, param, ref)
    except ValidationError:
        msg = (
            f"Validation error at {ref}: entity_property_dropdown param {param} failed"
            "to validate a string"
        )
        raise ValidationError(msg) from None


def validate_reference(schema: dict, param: str, ref: str) -> None:
    if (refref := schema.get("anyOf", [{}])[0].get("$ref")) is None:
        ref_schema = resolve_ref(openapi_schema, refref)
        msg = (
            f"Validation error at {ref}: ref param {param} should"
            "be a union with an 'reference class' as first element"
        )

        from pprint import pprint

        pprint(ref_schema)
        raise ValidationError(msg) from None

    validate_string(schema, "reference_type", f"{param} at {ref}")


def validate_block_elements(param: str, schema: dict, ref: str) -> None:
    match ui_element := schema.get("ui_element"):
        case "string_input":
            validate_string_param(schema, param, ref)
        case "float_parameter_sweep":
            validate_float_param_sweep(schema, param, ref)
        case "int_parameter_sweep":
            validate_int_param_sweep(schema, param, ref)
        case "entity_property_dropdown":
            validate_entity_property_dropdown(schema, param, ref)
        case "reference":
            validate_reference(schema, param, ref)
        case "neuron_ids":
            pass
        case "model_identifier":
            pass
        case _:
            msg = (
                f"Validation error at {ref}, param {param}: {ui_element} is not a valid ui_element"
            )
            raise ValueError(msg)


def validate_block(schema: dict, ref: str) -> None:
    validate_hidden_refs_not_required(schema, ref)

    validate_string(schema, "title", ref)
    validate_string(schema, "description", ref)

    for param, param_schema in schema.get("properties", {}).items():
        if param_schema.get("ui_hidden"):
            continue

        if param == "type":
            validate_type(param_schema, ref)
            continue

        validate_block_elements(param, param_schema, ref)
