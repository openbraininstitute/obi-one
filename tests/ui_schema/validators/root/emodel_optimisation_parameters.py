"""Validator for the `emodel_optimisation_parameters` root UI element.

This root element's UI is built entirely custom on the frontend and is NOT rendered from the
schema, so most of its nested fields carry no schema-driven UI metadata. What is validated here
is the data the frontend reads directly from the schema: the ``mechanisms.ion_channel_models``
selector, the section-list ``choices`` on ``mechanism_regions``, and the ``global_parameters``
default.

**This module is locked.** Root elements render an entire block and drive main-panel behaviour,
so weakening a check here has a large blast radius. Fix the config to match the spec; changing
the spec requires the `change-validators` label.
"""

from obi_one.core.schema import SchemaKey, UIElement

from .shared import openapi_schema, resolve_ref
from tests.ui_schema.validate_block import validate_block_elements

# Every section-list choice object the frontend renders must expose these keys, each with
# the given JSON type.
SECTION_LIST_CHOICE_TYPES: dict[str, type] = {
    "availability": str,
    "available": bool,
    "description": str,
    "display_order": int,
    "label": str,
    "name": str,
}
SECTION_LIST_CHOICE_KEYS = frozenset(SECTION_LIST_CHOICE_TYPES)


def validate_section_list_choice(choice: object, key: str, ref: str) -> None:
    """Validate a single section-list choice object's keys and value types."""
    if not isinstance(choice, dict):
        msg = (
            f"Validation error at {ref}: {key} 'choices' items must be objects. Got: {type(choice)}"
        )
        raise TypeError(msg)

    choice_dict: dict = choice
    missing = SECTION_LIST_CHOICE_KEYS - choice_dict.keys()
    if missing:
        msg = (
            f"Validation error at {ref}: {key} 'choices' item {choice_dict.get('name')!r} is "
            f"missing required keys: {sorted(missing)}"
        )
        raise ValueError(msg)

    for field, expected_type in SECTION_LIST_CHOICE_TYPES.items():
        # `bool` is a subclass of `int`, so compare the exact type of each value.
        if type(choice_dict[field]) is not expected_type:
            msg = (
                f"Validation error at {ref}: {key} choice {field!r} must be a "
                f"{expected_type.__name__}"
            )
            raise TypeError(msg)


def validate_section_list_property_names(schema: dict, key: str, ref: str) -> None:
    """Enforce that a section-list dict field constrains its keys with a ``propertyNames`` enum.

    ``mechanism_regions`` is keyed by ``SectionListName``, so the generated schema must expose a
    ``propertyNames`` with a non-empty string ``enum`` of the allowed section-list names. Locking
    this in keeps a future refactor from silently dropping the key constraint (which would let the
    frontend and stored configs use arbitrary, unvalidated region keys).
    """
    property_names = schema.get("propertyNames")
    if property_names is None:
        msg = f"Validation error at {ref}: {key} must expose a 'propertyNames' schema"
        raise ValueError(msg)

    # Pydantic emits the key enum as a `$ref` to the shared SectionListName definition.
    if property_names_ref := property_names.get("$ref"):
        property_names = {**property_names, **resolve_ref(openapi_schema, property_names_ref)}

    enum = property_names.get("enum")
    if enum is None:
        msg = f"Validation error at {ref}: {key} 'propertyNames' must expose an 'enum'"
        raise ValueError(msg)

    if not isinstance(enum, list) or not enum:
        msg = (
            f"Validation error at {ref}: {key} 'propertyNames.enum' must be a non-empty list. "
            f"Got: {enum}"
        )
        raise ValueError(msg)

    if not all(isinstance(name, str) for name in enum):
        msg = f"Validation error at {ref}: {key} 'propertyNames.enum' must contain only strings"
        raise TypeError(msg)

    # The key enum and the `choices` list describe the same section lists, so they must agree.
    choice_names = {choice.get("name") for choice in schema.get("choices", [])}
    if choice_names and set(enum) != choice_names:
        msg = (
            f"Validation error at {ref}: {key} 'propertyNames.enum' must match the section-list "
            f"'choices' names. Enum: {sorted(enum)}, choices: {sorted(choice_names)}"
        )
        raise ValueError(msg)


def validate_section_list_choices(schema: dict, key: str, ref: str) -> None:
    """Enforce that a section-list field exposes a well-formed ``choices`` list.

    ``choices`` drives the custom Task 2 frontend (it is not rendered from the schema),
    so it must exist, be a list, and every element must carry the availability/label
    metadata the frontend depends on. The dict's keys are additionally constrained by a
    ``propertyNames`` enum, validated here so it can never be dropped in a later refactor.
    """
    choices = schema.get("choices")
    if choices is None:
        msg = f"Validation error at {ref}: {key} must expose a 'choices' list"
        raise ValueError(msg)

    if not isinstance(choices, list):
        msg = f"Validation error at {ref}: {key} 'choices' must be a list. Got: {type(choices)}"
        raise TypeError(msg)

    if not choices:
        msg = f"Validation error at {ref}: {key} 'choices' must not be empty"
        raise ValueError(msg)

    for choice in choices:
        validate_section_list_choice(choice, key, ref)

    validate_section_list_property_names(schema, key, ref)


def validate_emodel_optimisation_parameters(
    schema: dict,
    element: str,  # ruff: ignore[unused-function-argument]
    ref: str,
    config_ref: str,  # ruff: ignore[unused-function-argument]
    form: dict,  # ruff: ignore[unused-function-argument]
) -> None:
    """Validate the root-level Task 2 mechanisms/optimization-parameter workflow element.

    Uniform root-validator signature (schema, element, ref, config_ref, form); this element
    validates in place from `ref`, so the element/config_ref/form context is unused here.

    This root element's UI is built entirely custom on the frontend and is NOT rendered from the
    schema (its tabs do not even correspond to the schema's nested structure), so most of its
    nested fields carry no schema-driven UI metadata.

    The one exception is ``mechanisms.ion_channel_models``, which is a normal
    ``model_identifier_multiple`` selector; its ui_element is validated here. The data the
    frontend reads from the schema is validated too: the section-list ``choices`` and the
    ``global_parameters`` default.
    """

    def resolve(node: dict) -> dict:
        node_ref = node.get("$ref")
        return {**node, **resolve_ref(openapi_schema, node_ref)} if node_ref else node

    mechanisms = schema.get("properties", {}).get("mechanisms")
    if mechanisms is None:
        msg = f"Validation error at {ref}: emodel_optimisation_parameters must have a 'mechanisms'"
        raise ValueError(msg)
    mechanisms = resolve(mechanisms)

    ion_channel_models = mechanisms.get("properties", {}).get("ion_channel_models")
    if ion_channel_models is None:
        msg = (
            f"Validation error at {ref}: emodel_optimisation_parameters mechanisms must have an "
            "'ion_channel_models' property"
        )
        raise ValueError(msg)

    if ion_channel_models.get(SchemaKey.UI_ELEMENT) != UIElement.MODEL_IDENTIFIER_MULTIPLE:
        msg = (
            f"Validation error at {ref}: emodel_optimisation_parameters "
            f"mechanisms.ion_channel_models must be a '{UIElement.MODEL_IDENTIFIER_MULTIPLE}'"
        )
        raise ValueError(msg)

    validate_block_elements("ion_channel_models", ion_channel_models, ref)

    mechanism_regions = mechanisms.get("properties", {}).get("mechanism_regions")
    if mechanism_regions is None:
        msg = (
            f"Validation error at {ref}: emodel_optimisation_parameters mechanisms must have a "
            "'mechanism_regions' property"
        )
        raise ValueError(msg)
    validate_section_list_choices(resolve(mechanism_regions), "mechanism_regions", ref)

    # The frontend's Global Parameters tab reads this default.
    if "default" not in schema.get("properties", {}).get("global_parameters", {}):
        msg = (
            f"Validation error at {ref}: emodel_optimisation_parameters global_parameters must "
            "have a 'default'"
        )
        raise ValueError(msg)
