import logging
import math
import sys

from fastapi.openapi.utils import get_openapi
from jsonschema import Draft7Validator, RefResolver, ValidationError, validate

from app.application import app

L = logging.getLogger()

openapi_schema = get_openapi(
    title=app.title,
    version=app.version,
    openapi_version=app.openapi_version,
    description=app.description,
    routes=app.routes,
)


def resolve_ref(openapi_schema: dict, ref: str) -> dict:
    resolver = RefResolver.from_schema(openapi_schema)
    _, resolved_node = resolver.resolve(ref)
    return resolved_node


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


def determine_minimum_valid_numeric_value(schema: dict) -> float | int:
    default = schema.get("default")
    single_type = schema.get("anyOf", [{}])[0]

    if single_type.get("type") == "integer":
        minimum = single_type.get("minimum", None)
        if minimum is None:
            minimum = single_type.get("exclusiveMinimum", -sys.maxsize)
            minimum += 1

        maximum = single_type.get("maximum", None)
        if maximum is None:
            maximum = single_type.get("exclusiveMaximum", sys.maxsize)
            maximum -= 1

    elif single_type.get("type") == "number":
        minimum = single_type.get("minimum", None)
        if minimum is None:
            minimum = single_type.get("exclusiveMinimum", -sys.float_info.max)
            minimum += math.ulp(minimum)

        maximum = single_type.get("maximum", None)
        if maximum is None:
            maximum = single_type.get("exclusiveMaximum", sys.float_info.max)
            maximum -= math.ulp(maximum)

    # Logical check if minimum less than or equal to maximum
    if not minimum <= maximum:
        msg = "minimum is not less than or equal maximum, invalid schema"
        raise ValidationError(msg)

    # Logical checks for default consistency
    if default is not None and not minimum <= default <= maximum:
        msg = "default is less than minimum or greater than maximum, invalid schema"
        raise ValidationError(msg)

    return minimum


def validate_numeric_single_and_list_types(
    schema: dict, param: str, ref: str, data_type: str, ui_element: str
) -> None:
    if schema.get("anyOf", [{}])[0].get("type") != data_type:
        msg = (
            f"Validation error at {ref}: {ui_element} param {param} should "
            f"be a union with a '{data_type}' as first element"
        )
        raise ValidationError(msg) from None

    if schema.get("anyOf", [{}])[1].get("type") != "array":
        msg = (
            f"Validation error at {ref}: {ui_element} param {param} should "
            "be a union with an 'array' as second element"
        )
        raise ValidationError(msg) from None

    if schema.get("anyOf", [{}])[0] != schema.get("anyOf", [{}])[1].get("items"):
        msg = (
            f"Validation error at {ref}: {ui_element} param {param} should "
            "have matching types for single value and array items"
        )
        raise ValidationError(msg) from None


def validate_float_param_sweep(schema: dict, param: str, ref: str) -> None:
    validate_numeric_single_and_list_types(schema, param, ref, "number", "float_parameter_sweep")
    test_value = determine_minimum_valid_numeric_value(schema)

    try:
        validate(test_value, schema)

    except ValidationError:
        msg = (
            f"Validation error at {ref}: float_parameter_sweep param {param} failed "
            "to validate a float"
        )
        raise ValidationError(msg) from None

    try:
        validate([test_value], schema)

    except ValidationError:
        msg = (
            f"Validation error at {ref}: float_parameter_sweep param {param} failed "
            "to validate a float array"
        )
        raise ValidationError(msg) from None


def validate_int_param_sweep(schema: dict, param: str, ref: str) -> None:
    validate_numeric_single_and_list_types(schema, param, ref, "integer", "int_parameter_sweep")
    test_value = determine_minimum_valid_numeric_value(schema)
    try:
        validate(test_value, schema)

    except ValidationError:
        msg = (
            f"Validation error at {ref}: int_parameter_sweep param {param} failed "
            "to validate an int"
        )
        raise ValidationError(msg) from None

    try:
        validate([test_value], schema)

    except ValidationError:
        msg = (
            f"Validation error at {ref}: int_parameter_sweep param {param} failed "
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
    validate_string(schema, "reference_type", f"{param} at {ref}")

    reference_type = schema.get("reference_type")

    schema_union = schema.get("anyOf", [])

    if len(schema_union) != 2 or (refref := schema_union[0].get("$ref")) is None:
        msg = (
            f"Validation error at {ref}: 'reference' param {param} should "
            "be a union with a 'BlockReference' as first element"
        )
        raise ValidationError(msg) from None

    ref_schema = resolve_ref(openapi_schema, refref)

    if (
        ref_type := ref_schema.get("properties", [{}]).get("type", {}).get("default")
    ) != reference_type:
        msg = (
            f"Validation error at {ref}: reference param {param} should "
            "contain a default type consistent with 'reference_type': "
            f"Expected {reference_type}, got {ref_type}"
        )
        raise ValidationError(msg) from None

    resolver = RefResolver.from_schema(openapi_schema)
    validator = Draft7Validator(schema, resolver=resolver)

    validated_ref = {"block_name": "test", "block_dict_name": "test"}
    try:
        validator.validate(validated_ref, schema)

    except ValidationError:
        msg = (
            f"Validation error at {refref}: 'reference' param {param} failed to validate a "
            f"reference object {validated_ref}"
        )
        raise ValidationError(msg) from None

    try:
        validator.validate(None, schema)

    except ValidationError:
        msg = (
            f"Validation error at {refref}: 'reference' param {param} failed to validate a "
            "'null' value"
        )
        raise ValidationError(msg) from None


def validate_string_selection(schema: dict, param: str, ref: str) -> None:
    # Make sure type
    if schema.get("type") != "string":
        msg = (
            f"Validation error at {ref}: string_dropdown param {param} should "
            "be a union with a 'string' as first element"
        )
        raise ValidationError(msg) from None

    enum_list = schema.get("enum")

    # Make sure enum field exists
    if enum_list is None:
        msg = (
            f"Validation error at {ref}: string_dropdown param {param} should "
            "have an 'enum' field in its schema"
        )
        raise ValidationError(msg) from None

    # Make sure enum is a non-empty list
    if type(enum_list) is not list or len(enum_list) == 0:
        msg = (
            f"Validation error at {ref}: string_dropdown param {param} should "
            "have a non-empty list as its 'enum' field"
        )
        raise ValidationError(msg) from None

    # Makesure all the values in the enum are strings
    for val in enum_list:
        if not isinstance(val, str):
            msg = (
                f"Validation error at {ref}: string_dropdown param {param} has "
                f"an enum value {val} that is not a string"
            )
            raise ValidationError(msg) from None

    # Try validating a single string value
    try:
        validate(enum_list[0], schema)
    except ValidationError:
        msg = (
            f"Validation error at {ref}: string_dropdown param {param} failed to validate a string"
        )
        raise ValidationError(msg) from None


def validate_enhanced_string_fields(schema: dict, param: str, ref: str) -> None:
    description_by_key = schema.get("description_by_key")
    latex_by_key = schema.get("latex_by_key")

    enum_list = schema.get("enum", [])

    if description_by_key is None:
        msg = (
            f"Validation error at {ref}: enhanced string param {param} should "
            "have a 'description_by_key' field in its schema"
        )
        raise ValidationError(msg) from None

    if latex_by_key is None:
        msg = (
            f"Validation error at {ref}: enhanced string param {param} should "
            "have a  'latex_by_key' field in its schema"
        )
        raise ValidationError(msg) from None

    for key in enum_list:
        if key not in description_by_key:
            msg = (
                f"Validation error at {ref}: enhanced string param {param} is missing "
                f"a description for key '{key}' in 'description_by_key'"
            )
            raise ValidationError(msg) from None

        if key not in latex_by_key:
            msg = (
                f"Validation error at {ref}: enhanced string param {param} is missing "
                f"a latex entry for key '{key}' in 'latex_by_key'"
            )
            raise ValidationError(msg) from None


def validate_string_selection_enhanced(schema: dict, param: str, ref: str) -> None:
    validate_string_selection(schema=schema, param=param, ref=ref)
    validate_enhanced_string_fields(schema=schema, param=param, ref=ref)


def validate_string_constant(schema: dict, param: str, ref: str) -> None:
    # Make sure type
    if schema.get("type") != "string":
        msg = f"Validation error at {ref}: string_constant param {param} should be of type 'string'"
        raise ValidationError(msg) from None

    const_value = schema.get("const")

    # Make sure const field exists
    if const_value is None:
        msg = (
            f"Validation error at {ref}: string_constant param {param} should "
            "have a 'const' field in its schema"
        )
        raise ValidationError(msg) from None

    # Make sure const is a string
    if not isinstance(const_value, str):
        msg = (
            f"Validation error at {ref}: string_constant param {param} should "
            "have a string as its 'const' field"
        )
        raise ValidationError(msg) from None

    # Try validating the constant value
    try:
        validate(const_value, schema)
    except ValidationError:
        msg = (
            f"Validation error at {ref}: string_constant param {param} failed to validate a string"
        )
        raise ValidationError(msg) from None


def validate_string_constant_enhanced(schema: dict, param: str, ref: str) -> None:
    validate_string_constant(schema=schema, param=param, ref=ref)
    validate_enhanced_string_fields(schema=schema, param=param, ref=ref)


def validate_neuron_ids(schema: dict, param: str, ref: str) -> None:
    resolver = RefResolver.from_schema(openapi_schema)
    validator = Draft7Validator(schema, resolver=resolver)

    neuron_ids = {"elements": [1]}
    try:
        validator.validate(neuron_ids)
    except ValidationError:
        msg = (
            f"Validation error at {ref}: 'neuron_ids' param {param} failed to validate a "
            f"neuron_ids object {neuron_ids}"
        )
        raise ValidationError(msg) from None


def validate_model_identifier(schema: dict, param: str, ref: str) -> None:
    resolver = RefResolver.from_schema(openapi_schema)
    validator = Draft7Validator(schema, resolver=resolver)

    obj = {"id_str": "model_id"}

    try:
        validator.validate(obj)
    except ValidationError:
        msg = (
            f"Validation error at {ref}: 'model_identtifier' param {param} failed to validate a "
            f"a 'model identifier' object {obj}"
        )
        raise ValidationError(msg) from None


def validate_boolean_input(schema: dict, param: str, ref: str) -> None:
    if schema.get("type") != "boolean":
        msg = f"Validation error at {ref}: boolean_input param {param} should have type 'boolean'"
        raise ValidationError(msg)

    test_true = True
    test_false = False

    try:
        validate(test_true, schema)
    except ValidationError:
        msg = f"Validation error at {ref}: boolean_input param {param} failed to validate True"
        raise ValidationError(msg) from None

    try:
        validate(test_false, schema)
    except ValidationError:
        msg = f"Validation error at {ref}: boolean_input param {param} failed to validate False"
        raise ValidationError(msg) from None


def validate_block_elements(param: str, schema: dict, ref: str) -> None:  # noqa: PLR0912, C901
    match ui_element := schema.get("ui_element"):
        case "string_input":
            validate_string_param(schema, param, ref)
        case "boolean_input":
            validate_boolean_input(schema, param, ref)
        case "float_parameter_sweep":
            validate_float_param_sweep(schema, param, ref)
        case "int_parameter_sweep":
            validate_int_param_sweep(schema, param, ref)
        case "entity_property_dropdown":
            validate_entity_property_dropdown(schema, param, ref)
        case "reference":
            validate_reference(schema, param, ref)
        case "string_selection":
            validate_string_selection(schema, param, ref)
        case "string_selection_enhanced":
            validate_string_selection_enhanced(schema, param, ref)
        case "string_constant":
            validate_string_constant(schema, param, ref)
        case "string_constant_enhanced":
            validate_string_constant_enhanced(schema, param, ref)
        case "neuron_ids":
            validate_neuron_ids(schema, param, ref)
        case "model_identifier":
            validate_model_identifier(schema, param, ref)
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

        validate_string(param_schema, "title", f"{param} at {ref}")
        validate_string(param_schema, "description", f"{param} at {ref}")
        validate_block_elements(param, param_schema, ref)
