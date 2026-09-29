"""Lifecycle helpers for circuit registration / validation."""

from enum import StrEnum
from typing import Any

from entitysdk.types import EntityLifecycleStatus


class CircuitValidationMode(StrEnum):
    """How a circuit gets validated when it is registered.

    Attributes:
        sync_bluepysnap: Run the bluepysnap SONATA check in this process, before registering.
        sync_neurodamus: Register the circuit as ``draft``, then run the MOD compile, HOC and
            snap checks in this process. The circuit ends up ``active`` or ``disqualified``.
        async_launch: Register the circuit as ``draft`` and let a launch-system job validate
            it later. That job sets the final lifecycle status.
        skip: Do not validate.
    """

    sync_bluepysnap = "sync_bluepysnap"
    sync_neurodamus = "sync_neurodamus"
    async_launch = "async_launch"
    skip = "skip"


def is_validation_allowed(*, lifecycle_status: Any, force: bool = False) -> bool:
    """Return whether circuit validation may proceed for the given lifecycle status.

    Validation is allowed when:
    - ``force`` is True,
    - ``lifecycle_status`` is unset/None, or
    - ``lifecycle_status`` is ``draft``.
    """
    if force or lifecycle_status is None:
        return True
    if lifecycle_status == EntityLifecycleStatus.draft:
        return True
    return str(lifecycle_status) == "draft"


def validation_blocked_detail(lifecycle_status: Any) -> str:
    """Human-readable detail when validation is blocked by lifecycle status."""
    return (
        f"Circuit lifecycle_status is '{lifecycle_status}'. "
        "Validation requires draft status, or pass force=true to overwrite."
    )
