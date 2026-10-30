import itertools
import logging
import math
from typing import TYPE_CHECKING, Self

from pydantic import GetJsonSchemaHandler, PrivateAttr
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from obi_one.core.base import OBIBaseModel
from obi_one.core.block_subunit.complex_variable_holder import ComplexVariableHolder
from obi_one.core.param import MultiValueScanParam
from obi_one.core.parametric_multi_values import MAX_N_COORDINATES, ParametericMultiValue
from obi_one.utils.pydantic import order_schema_properties

if TYPE_CHECKING:
    from obi_one.core.block_reference import BlockReference


L = logging.getLogger(__name__)


class Block(OBIBaseModel, extra="forbid"):
    """Defines a component of a ScanConfig.

    Parameters can be of type | list[type]
    when a list is used it is used as a dimension in a multi-dimensional parameter scan.
    Tuples should be used when list-like parameter is needed.
    """

    _multiple_value_parameters: list[MultiValueScanParam] = PrivateAttr(default=[])
    _ref = None
    _block_name = None

    @classmethod
    def __get_pydantic_json_schema__(  # ruff: ignore[bad-dunder-method-name]
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        """Order the schema properties by priority when generating the JSON schema."""
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        return order_schema_properties(json_schema)

    @property
    def block_name(self) -> str:
        """The block name."""
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
            if isinstance(value, ComplexVariableHolder):
                self._multiple_value_parameters.extend(
                    value.multiple_value_parameters(
                        base_location_list=[category_name, block_key, key]
                        if block_key
                        else [category_name, key]
                    )
                )
                continue

            if isinstance(value, ParametericMultiValue):
                multi_values = list(value)

            elif isinstance(value, list):
                # list[ComplexVariableHolder] special case
                if len(value) > 0 and isinstance(value[0], ComplexVariableHolder):
                    for i, complex_variable_holder in enumerate(value):
                        self._multiple_value_parameters.extend(
                            complex_variable_holder.multiple_value_parameters(
                                base_location_list=[category_name, block_key, key, i]
                                if block_key
                                else [category_name, key, i]
                            )
                        )
                    continue
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

    def expand_multi_values(self, max_n: int = MAX_N_COORDINATES) -> list[Self]:
        """Expands multi-value parameters into single-valued copies of this block.

        A list in a block field is a parameter scan dimension: a ScanConfig sweeps it
        into one single config per value. This method performs the same expansion for a
        standalone block, producing the Cartesian product of its multi-value parameters
        (plain lists and ParametericMultiValue ranges) as single-valued copies. It is
        used when a block is consumed outside a scan (e.g., by declared endpoints) but
        may still carry swept fields.

        Args:
            max_n: Maximum number of single-valued blocks allowed.

        Returns:
            Single-valued copies of this block. ``[self]`` when there are no
            multi-value parameters.

        Raises:
            ValueError: If the number of combinations exceeds ``max_n``, or if a
                multi-value parameter is nested inside a ComplexVariableHolder
                (only top-level fields are supported).
        """
        params = self.multiple_value_parameters(category_name="block")
        if not params:
            return [self]

        top_level_location_len = 2  # [category_name, field_name]
        for param in params:
            if len(param.location_list) != top_level_location_len:
                msg = f"Cannot expand nested multi-value parameter '{param.location_str}'."
                raise ValueError(msg)

        n_combinations = math.prod(len(param.values) for param in params)
        if n_combinations > max_n:
            msg = (
                f"Number of single-valued blocks {n_combinations} exceeds maximum allowed {max_n}."
            )
            raise ValueError(msg)

        return [
            self.model_copy(
                update={
                    param.location_list[1]: value
                    for param, value in zip(params, combination, strict=True)
                },
                deep=True,
            )
            for combination in itertools.product(*(param.values for param in params))
        ]
