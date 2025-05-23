from typing import Any

from pydantic import Field

from obi_one.core.base import OBIBaseModel


def nested_param_short(nested_param_list: list) -> str:
    """Convert a list of nested parameters to a short string representation."""
    nested_param_short = ""
    for i, s in enumerate(nested_param_list):
        nested_param_short += f"{s}"
        if i < len(nested_param_list) - 1:
            nested_param_short += "."
    return nested_param_short


class ScanParam(OBIBaseModel):
    location_list: list = Field(default_factory=list)
    _location_str: str = ""

    @property
    def location_str(self) -> str:
        """Return a string representation of the location list."""
        return nested_param_short(self.location_list)


class MultiValueScanParam(ScanParam):
    values: list[Any] = Field(default_factory=lambda: [None])


class SingleValueScanParam(ScanParam):
    value: Any
