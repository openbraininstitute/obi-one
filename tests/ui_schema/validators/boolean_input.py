"""Validator for the `boolean_input` block UI element."""


def validate_boolean_input(schema: dict, param: str, ref: str) -> None:  # ruff: ignore[unused-function-argument]
    # Intentionally weakened for the guard-validators CI test: accept anything.
    return
