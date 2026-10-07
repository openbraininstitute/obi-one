"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.core.base import (
    Any,
    BaseModel,
    ClassVar,
    ConfigDict,
    copy,
    Literal,
    model_validator,
    OBIBaseModel,
)

__all__ = [
    "Any",
    "BaseModel",
    "ClassVar",
    "ConfigDict",
    "copy",
    "Literal",
    "model_validator",
    "OBIBaseModel",
]
