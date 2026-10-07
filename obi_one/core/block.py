"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.core.block import (
    Block,
    ComplexVariableHolder,
    CoreSchema,
    GetJsonSchemaHandler,
    JsonSchemaValue,
    L,
    logging,
    MultiValueScanParam,
    OBIBaseModel,
    order_schema_properties,
    ParametericMultiValue,
    PrivateAttr,
    TYPE_CHECKING,
)

__all__ = [
    "Block",
    "ComplexVariableHolder",
    "CoreSchema",
    "GetJsonSchemaHandler",
    "JsonSchemaValue",
    "L",
    "logging",
    "MultiValueScanParam",
    "OBIBaseModel",
    "order_schema_properties",
    "ParametericMultiValue",
    "PrivateAttr",
    "TYPE_CHECKING",
]
