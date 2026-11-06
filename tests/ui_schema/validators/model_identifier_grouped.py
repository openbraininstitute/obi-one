"""Validator for the `model_identifier_grouped` block UI element."""

from jsonschema import Draft7Validator, RefResolver, ValidationError

from .shared import openapi_schema, resolve_ref


def validate_model_identifier_grouped(schema: dict, param: str, ref: str) -> None:
    """Validate a grouped model-identifier field (case D of the multiple-entities spec).

    The field is a NamedTuple group or a list of them:
    ``anyOf: [ {$ref: Group}, {type: array, items: {$ref: Group}} ]``. Each group carries a
    ``name`` string and an ``elements`` array of model-identifier (``{"id_str": ...}``) objects.
    The single-group and list-of-groups branches must reference the same group schema so the two
    ways of storing the value stay in sync.
    """
    any_of = schema.get("anyOf")
    if not isinstance(any_of, list) or len(any_of) != 2:
        msg = (
            f"Validation error at {ref}: model_identifier_grouped param {param} should be an "
            "'anyOf' of a group and an array of groups"
        )
        raise ValidationError(msg)

    single_branch, array_branch = any_of
    group_ref = single_branch.get("$ref")
    array_items_ref = array_branch.get("items", {}).get("$ref")
    if group_ref is None or array_branch.get("type") != "array" or array_items_ref != group_ref:
        msg = (
            f"Validation error at {ref}: model_identifier_grouped param {param} should reference "
            "the same group schema for its single-group and list-of-groups branches"
        )
        raise ValidationError(msg)

    group_schema = resolve_ref(openapi_schema, group_ref)
    group_props = group_schema.get("properties", {})

    if group_props.get("name", {}).get("type") != "string":
        msg = (
            f"Validation error at {ref}: model_identifier_grouped param {param} group should have "
            "a 'name' string"
        )
        raise ValidationError(msg)

    elements = group_props.get("elements", {})
    if elements.get("type") != "array":
        msg = (
            f"Validation error at {ref}: model_identifier_grouped param {param} group should have "
            "an 'elements' array"
        )
        raise ValidationError(msg)

    # Each element must validate a model-identifier ({"id_str": ...}) object.
    resolver = RefResolver.from_schema(openapi_schema)
    validator = Draft7Validator(elements.get("items", {}), resolver=resolver)
    obj = {"id_str": "model_id"}
    try:
        validator.validate(obj)
    except ValidationError:
        msg = (
            f"Validation error at {ref}: model_identifier_grouped param {param} group elements "
            f"failed to validate a 'model identifier' object {obj}"
        )
        raise ValidationError(msg) from None
