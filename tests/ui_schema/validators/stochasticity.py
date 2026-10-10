"""Validator for the `stochasticity` block UI element."""

from jsonschema import ValidationError

from .shared import accepts


def validate_stochasticity(schema: dict, param: str, ref: str) -> None:
    # One-off element for the `stochasticity` field (``bool | tuple[str, ...]``). The value is
    # either a boolean (enable/disable globally) or a list of protocol names (enable only for
    # those protocols). The protocol names are matched downstream by BluePyEModel; rendering them
    # from the selected extraction result is deferred to a future dynamic-dropdown element, so the
    # list is validated only by shape here (a list of strings).
    accepted = (True, False, ["a"])
    rejected = ("a", [1])
    if not all(accepts(schema, value) for value in accepted) or any(
        accepts(schema, value) for value in rejected
    ):
        msg = (
            f"Validation error at {ref}: stochasticity param {param} should validate a boolean "
            f"or a list of strings and nothing else"
        )
        raise ValidationError(msg) from None
