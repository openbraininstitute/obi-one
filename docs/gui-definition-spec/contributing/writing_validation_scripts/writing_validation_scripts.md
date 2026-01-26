### Writing validation scripts

For each new `ui_element` a corresponding validation function must be added to [validate_root_element](../../../../tests/schema/test_schema.py) in case of new root elements or to [validate_block_elements](../../../../tests/schema/validate_block.py) in the case of new block elements.

The purpose of validation functions is twofold:
1. Ensure that the schema of the element matches the structure the frontend needs to render the input element.
2. Ensure the element accepts as input the types the frontend is expected to produce.


For example [block dictionaries](../../gui-definition.md#types-of-ui-element) require that the `oneOf` property is present in the schema, since it renders the elements of that array, therefore the script must check it exists:

```py
def validate_block_dictionary(schema: dict, key: str, config_ref: str) -> None:
    if schema.get("additionalProperties", {}).get("oneOf") is None:
        msg = (
            f"Validation error at {config_ref}: block_dictionary {key} must have 'oneOf'"
            "in additionalProperties"
        )
        raise ValueError(msg)

    ...

```

To check the expected input types are accepted by the `ui_element` one can simply use `validate` from the `jsonschema` library. 
For example the `float_parameter_sweep` must accept a `float` or a `list[float]`, so that's what we check:

```py
def validate_float_param_sweep(param_schema: dict, param: str, ref: str) -> None:
     
    ##... We check input types after checking the schema structure

    try:
        validate(1.0, param_schema)

    except ValidationError:
        msg = (
                f"Validation error at {ref}: float_parameter_sweep param {param} failed "
                "to validate a float"
            )
        raise ValidationError(msg) from None

    try:
        validate([1.0], param_schema)

    except ValidationError:
        msg = (
                f"Validation error at {ref}: float_parameter_sweep param {param} failed "
                "to validate a float array"
            )
        raise ValidationError(msg) from None
```
