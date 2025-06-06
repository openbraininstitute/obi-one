from pydantic import PrivateAttr

from obi_one.core.base import OBIBaseModel
from obi_one.core.param import MultiValueScanParam


class Block(OBIBaseModel):
    """Defines a component of a Form.

    Parameters can be of type | list[type]
    when a list is used it is used as a dimension in a multi-dimensional parameter scan.
    Tuples should be used when list-like parameter is needed.
    """

    _multiple_value_parameters: list[MultiValueScanParam] = PrivateAttr(default=[])

    def multiple_value_parameters(
        self, category_name: str, block_key: str = ""
    ) -> list[MultiValueScanParam]:
        """Return a list of MultiValueScanParam objects for the block."""
        self._multiple_value_parameters = []

        for key, value in self.__dict__.items():
            if isinstance(value, list):  # and len(value) > 1:
                multi_values = value
                if block_key:
                    self._multiple_value_parameters.append(
                        MultiValueScanParam(
                            location_list=[category_name, block_key, key], values=multi_values
                        )
                    )
                else:
                    self._multiple_value_parameters.append(
                        MultiValueScanParam(location_list=[category_name, key], values=multi_values)
                    )

        return self._multiple_value_parameters

    def enforce_no_lists(self) -> None:
        """Raise a TypeError if any attribute is a list."""
        for key, value in self.__dict__.items():
            if isinstance(value, list):
                msg = f"Attribute '{key}' must not be a list."
                raise TypeError(msg)
