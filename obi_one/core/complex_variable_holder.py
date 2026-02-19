from abc import ABC

from obi_one.core.base import OBIBaseModel


class ComplexVariableHolder(OBIBaseModel, ABC):
    """Example model holding complex variables."""

    def set_properties_from_dictionary(self, data: dict) -> None:
        pass

    def multiple_value_parameters_list(self):
        pass
