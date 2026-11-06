"""Validator for the `neuron_set_combination` block UI element."""

from jsonschema import ValidationError

from obi_one.core.schema import SchemaKey
from obi_one.scientific.blocks.neuron_sets.combined import SetOperation

from .shared import resolve_union_reference_types, validate_list_strings


def validate_neuron_set_combination(schema: dict, param: str, ref: str) -> None:
    # `reference_types` declares the reference types offered for the neuron set element of each
    # (neuron set, set operation) pair.
    validate_list_strings(schema, SchemaKey.REFERENCE_TYPES, f"{param} at {ref}")
    reference_types = schema.get(SchemaKey.REFERENCE_TYPES)

    # The field is a list (array) of (neuron_set_reference, set_operation) 2-tuples.
    if schema.get("type") != "array":
        msg = (
            f"Validation error at {ref}: neuron_set_combination param {param} "
            "should be of type 'array'"
        )
        raise ValidationError(msg) from None

    item_schema = schema.get("items", {})
    prefix_items = item_schema.get("prefixItems", [])
    if (
        item_schema.get("type") != "array"
        or item_schema.get("minItems") != 2
        or item_schema.get("maxItems") != 2
        or len(prefix_items) != 2
    ):
        msg = (
            f"Validation error at {ref}: neuron_set_combination param {param} should have items "
            "that are 2-tuples of (neuron set reference, set operation)"
        )
        raise ValidationError(msg) from None

    # First tuple element: a (single or anyOf) union of BlockReferences whose default `type`
    # values must match the declared `reference_types` exactly.
    reference_member = prefix_items[0]
    union_members = reference_member.get("anyOf", [reference_member])
    union_reference_types = resolve_union_reference_types(union_members)
    if set(union_reference_types) != set(reference_types):
        msg = (
            f"Validation error at {ref}: neuron_set_combination param {param} should reference "
            "BlockReferences whose default 'type' values match 'reference_types': "
            f"Expected {reference_types}, got {union_reference_types}"
        )
        raise ValidationError(msg) from None

    # Second tuple element: the set operation, a string enum of the supported operations.
    operation_schema = prefix_items[1]
    expected_operations = {operation.value for operation in SetOperation}
    if (
        operation_schema.get("type") != "string"
        or set(operation_schema.get("enum", [])) != expected_operations
    ):
        msg = (
            f"Validation error at {ref}: neuron_set_combination param {param} should have a string "
            f"enum of set operations {sorted(expected_operations)} as its second tuple element, "
            f"got {operation_schema.get('enum')}"
        )
        raise ValidationError(msg) from None
