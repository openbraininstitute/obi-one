from typing import TYPE_CHECKING, ClassVar

from pydantic import PrivateAttr

from obi_one.core.base import OBIBaseModel
from obi_one.core.param import MultiValueScanParam
from obi_one.core.parametric_multi_values import ParametericMultiValue

if TYPE_CHECKING:
    from obi_one.core.block_reference import BlockReference


class Block(OBIBaseModel):
    """Defines a component of a ScanConfig.

    Parameters can be of type | list[type]
    when a list is used it is used as a dimension in a multi-dimensional parameter scan.
    Tuples should be used when list-like parameter is needed.
    """

    title: ClassVar[str | None] = None  # Optional: subclasses can override

    @classmethod
    def __init_subclass__(cls, **kwargs) -> None:
        """Initialize subclass."""
        super().__init_subclass__(**kwargs)

        # Use the subclass-provided title, or fall back to the class name
        cls.model_config = {"title": cls.title or cls.__name__}

    _multiple_value_parameters: list[MultiValueScanParam] = PrivateAttr(default=[])

    _ref = None
    _block_name = None

    @property
    def block_name(self) -> str:
        """Returns the block name."""
        if self._block_name is None:
            msg = "Block name has not been set. Please add the block to a form and validate."
            raise ValueError(msg)
        return self._block_name

    def set_block_name(self, name: str) -> None:
        self._block_name = name

    def has_block_name(self) -> bool:
        return self._block_name is not None

    @property
    def ref(self) -> "BlockReference":
        if self._ref is None:
            msg = "Block reference has not been set."
            raise ValueError(msg)
        return self._ref

    def set_ref(self, value: "BlockReference") -> None:
        self._ref = value

    def has_ref(self) -> bool:
        return self._ref is not None

    def multiple_value_parameters(
        self, category_name: str, block_key: str = ""
    ) -> list[MultiValueScanParam]:
        """Return a list of MultiValueScanParam objects for the block."""
        self._multiple_value_parameters = []

        for key, value in self.__dict__.items():
            if isinstance(value, ParametericMultiValue):
                multi_values = list(value)

            elif isinstance(value, list):
                multi_values = value

            else:
                continue

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

    def enforce_no_multi_param(self) -> None:
        """Raise a TypeError if any attribute is a list."""
        for key, value in self.__dict__.items():
            if isinstance(value, list):
                msg = f"Attribute '{key}' must not be a list."
                raise TypeError(msg)
            if isinstance(value, ParametericMultiValue):
                msg = f"Attribute '{key}' must not be a ParametericMultiValue."
                raise TypeError(msg)
