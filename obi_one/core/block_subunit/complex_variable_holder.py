from pydantic import Field, NonNegativeFloat, PrivateAttr

from obi_one.core.base import OBIBaseModel
from obi_one.core.param import MultiValueScanParam


class ComplexVariableHolder(OBIBaseModel, extra="forbid"):
    """Has structure List[Tuple[AnyOf(int, float, list[float], list[int])]]."""

    _multiple_value_parameters: list[MultiValueScanParam] = PrivateAttr(default=[])

    # checks this for parameter scan
    def multiple_value_parameters(self, base_location_list: list[str]) -> list[MultiValueScanParam]:
        self._multiple_value_parameters = []

        for key, value in self.__dict__.items():
            multi_values = []
            if isinstance(value, list):
                multi_values.append(
                    {
                        "value": value,
                        "location_list": [*base_location_list, key],
                    }
                )

            for multi_value in multi_values:
                self._multiple_value_parameters.append(
                    MultiValueScanParam(
                        location_list=multi_value["location_list"], values=multi_value["value"]
                    )
                )

        return self._multiple_value_parameters


class DurationVoltageCombination(ComplexVariableHolder):
    """Class for storing pairs of duration and voltage combinations for stimulation protocols."""

    voltage: float | list[float] = Field(
        title="Voltage for each level",
        description="The voltage for each level, given in millivolts (mV).",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "unit": "mV",
        },
    )

    duration: NonNegativeFloat | list[NonNegativeFloat] = Field(
        title="Duration for each level",
        description="The duration for each level, given in milliseconds (ms).",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "unit": "ms",
        },
    )
