"""Lifecycle helpers for circuit registration / validation."""

from typing import Any

from entitysdk.types import EntityLifecycleStatus


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
