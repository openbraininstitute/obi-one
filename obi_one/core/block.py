from pydantic import PrivateAttr
from typing import Optional

from obi_one.core.base import OBIBaseModel
from obi_one.core.param import MultiValueScanParam

from typing import ClassVar


class Block(OBIBaseModel):
    """Defines a component of a Form.

    Parameters can be of type | list[type]
    when a list is used it is used as a dimension in a multi-dimensional parameter scan.
    Tuples should be used when list-like parameter is needed.
    """

    title: ClassVar[Optional[str]] = None  # Optional: subclasses can override

    @classmethod
    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)

        # Use the subclass-provided title, or fall back to the class name
        cls.model_config = {
            "title": cls.title or cls.__name__
        }

    _multiple_value_parameters: list[MultiValueScanParam] = PrivateAttr(default=[])

    _simulation_level_name: Optional[str] = PrivateAttr(default=None)

    _ref = None

    def check_simulation_init(self):
        assert self._simulation_level_name is not None, (
            f"'{self.__class__.__name__}' initialization within a simulation required!"
        )

    @property
    def name(self):
        self.check_simulation_init()
        return self._simulation_level_name

    def has_name(self) -> bool:
        return self._simulation_level_name is not None

    def set_simulation_level_name(self, value: str):
        if not isinstance(value, str) or not value:
            raise ValueError("Simulation level name must be a non-empty string.")
        self._simulation_level_name = value

    @property
    def ref(self):
        if self._ref is None:
            raise ValueError("Block reference has not been set.")
        return self._ref
    
    def set_ref(self, value):
        self._ref = value


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
