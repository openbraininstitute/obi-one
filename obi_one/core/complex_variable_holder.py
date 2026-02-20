from abc import ABC

from obi_one.core.base import OBIBaseModel


class ComplexVariableHolder(OBIBaseModel, ABC):
    """Example model holding complex variables."""

    def set_properties_from_dictionary(self, data: dict) -> None:
        pass

    def multiple_value_parameters_list(self) -> list:
        pass



class ExampleComplexVariableHolder(ComplexVariableHolder):
    """Example implementation of ComplexVariableHolder."""

    param_a: int | list[int] = 0
    param_dict: dict[str, int | list[int]] = {}

    def set_properties_from_dictionary(self, data: dict) -> None:
        self.param_a = data.get("param_a", self.param_a)
        self.param_dict = data.get("param_dict", self.param_dict)

    def multiple_value_parameters_list(self) -> list:
        multiple_value_parameters_list = []
        # for key, value in self.data.items():


        return multiple_value_parameters_list
        # return self.data.get("multiple_value_parameters", [])