from pydantic import Field, NonNegativeFloat, PrivateAttr

from obi_one.core.base import OBIBaseModel
from obi_one.core.param import MultiValueScanParam
from obi_one.core.schema import SchemaKey
from obi_one.core.units import Units


class ComplexVariableHolder(OBIBaseModel, extra="forbid"):
    """Has structure List[Tuple[AnyOf(int, float, list[float], list[int])]]."""

    _multiple_value_parameters: list[MultiValueScanParam] = PrivateAttr(default=[])

    # checks this for parameter scan
    def multiple_value_parameters(self, base_location_list: list[str]) -> list[MultiValueScanParam]:
        self._multiple_value_parameters = []

        for key, value in self.__dict__.items():
            if isinstance(value, list):
                self._multiple_value_parameters.append(
                    MultiValueScanParam(location_list=[*base_location_list, key], values=value)
                )

        return self._multiple_value_parameters


class DurationVoltageCombination(ComplexVariableHolder):
    """Class for storing pairs of duration and voltage combinations for stimulation protocols."""

    voltage: float | list[float] = Field(
        title="Voltage for each level",
        description="The voltage for each level, given in millivolts (mV).",
        json_schema_extra={
            SchemaKey.UNITS: Units.MILLIVOLTS,
        },
    )

    duration: NonNegativeFloat | list[NonNegativeFloat] = Field(
        title="Duration for each level",
        description="The duration for each level, given in milliseconds (ms).",
        json_schema_extra={
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
