"""Validator for the `reference` block UI element."""

from jsonschema import Draft7Validator, RefResolver, ValidationError

from obi_one.core.schema import SchemaKey

from .shared import (
    openapi_schema,
    resolve_union_reference_types,
    validate_list_strings,
)


def validate_reference(schema: dict, param: str, ref: str) -> None:
    validate_list_strings(schema, SchemaKey.REFERENCE_TYPES, f"{param} at {ref}")

    reference_types = schema.get(SchemaKey.REFERENCE_TYPES)

    schema_union = schema.get("anyOf")
    schema_union = [{"$ref": schema.get("$ref")}] if schema_union is None else list(schema_union)

    non_null_refs = [
        union_member.get("$ref") for union_member in schema_union if union_member.get("$ref")
    ]
    if not non_null_refs:
        msg = (
            f"Validation error at {ref}: 'reference' param {param} should "
            "be a BlockReference or a union with a BlockReference as first element"
        )
        raise ValidationError(msg) from None

    allows_null = len(schema_union) == 2 and schema_union[1].get("type") == "null"

    # Each non-null member of the union is a $ref to a BlockReference whose
    # default `type` is its class name. Collect these and check they correspond
    # exactly to the declared `reference_types`.
    union_reference_types = resolve_union_reference_types(schema_union)

    if set(union_reference_types) != set(reference_types):
        msg = (
            f"Validation error at {ref}: reference param {param} should reference "
            "BlockReferences whose default 'type' values match 'reference_types': "
            f"Expected {reference_types}, got {union_reference_types}"
        )
        raise ValidationError(msg) from None

    resolver = RefResolver.from_schema(openapi_schema)
    validator = Draft7Validator(schema, resolver=resolver)

    validated_ref = {"block_name": "test", "block_dict_name": "test"}
    try:
        validator.validate(validated_ref, schema)

    except ValidationError:
        msg = (
            f"Validation error at {non_null_refs[0]}: 'reference' param {param} "
            "failed to validate a "
            f"reference object {validated_ref}"
        )
        raise ValidationError(msg) from None

    if allows_null:
        try:
            validator.validate(None, schema)

        except ValidationError:
            msg = (
                f"Validation error at {non_null_refs[0]}: 'reference' param {param} "
                "failed to validate a "
                "'null' value"
            )
            raise ValidationError(msg) from None
