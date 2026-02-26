from pydantic import Field, NonNegativeFloat, PrivateAttr

from obi_one.core.base import OBIBaseModel
from obi_one.core.param import MultiValueScanParam


class ComplexVariableHolder(OBIBaseModel, extra="forbid"):
    """Has structure List[Tuple[AnyOf(int, float, list[float], list[int])]]"""

    _multiple_value_parameters: list[MultiValueScanParam] = PrivateAttr(default=[])

    def multiple_value_parameters(
        self, base_location_list: list[str]
    ) -> list[MultiValueScanParam]:
        
        self._multiple_value_parameters = []

        for key, value in self.__dict__.items():
            # find the value of the form list[tuple(list[...])]
            # make parameter scan on the list inside the tuple
            multi_values = []
            if isinstance(value, list):
                for list_i, item in enumerate(value):
                    if isinstance(item, tuple):
                        for tuple_i, subitem in enumerate(item):
                            if isinstance(subitem, list):
                                multi_values.append(
                                    {
                                        "value": subitem,
                                        "location_list": base_location_list + [key, list_i, tuple_i],
                                    }
                                )

            for multi_value in multi_values:
                self._multiple_value_parameters.append(
                    MultiValueScanParam(
                        location_list=multi_value["location_list"], values=multi_value["value"]
                    )
                )

        return self._multiple_value_parameters
    

class DurationVoltageCombinations(ComplexVariableHolder):
    """Class for storing pairs of duration and voltage combinations for stimulation protocols."""
    
    voltage_durations: list[tuple[NonNegativeFloat | list[NonNegativeFloat], float | list[float]]] = Field(
        title="Duration and voltage combinations for each step",
        description="A list of duration and voltage combinations for each step of the SEClamp stimulus. \
                    Each combination specifies the duration and voltage level of a step input. \
                    The duration is given in milliseconds (ms) and the voltage is given in millivolts (mV).",
        json_schema_extra={
            "ui_element": "expandable_list",
            "subelement_ui_elements": ["float_parameter_sweep", "float_parameter_sweep"],
            "subelement_titles": ["Duration", "Voltage"],
            "subelement_units": ["ms", "mV"],
        },
    )
