from typing import Annotated, ClassVar, Self

import numpy as np
from pydantic import Field, NonNegativeFloat, PrivateAttr, model_validator

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.library.constants import (
    _DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
    _MAX_EFIELD_FREQUENCY_HZ,
    _MAX_SIMULATION_LENGTH_MILLISECONDS,
)
from obi_one.scientific.library.entity_property_types import (
    CircuitUsability,
    MappedPropertiesGroup,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    resolve_neuron_set_ref_to_node_set,
)

from .stimulus import ContinuousStimulus

_RAMP_QAULIFIER_DESCRIPTION = (
    "The duration does not include the ramp up and ramp down times, "
    "so the total length of the stimulus will be the sum of the duration, "
    "ramp up and ramp down times."
)


class SpatiallyUniformElectricFieldStimulus(ContinuousStimulus):
    """A spatially uniform electric field of fixed magnitude and direction.

    The stimulus is applied to all compartments of the selected Neuron Set.
    Neurons must be in a biophysical population.
    """

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.BLOCK_USABILITY_DICTIONARY: {
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitUsability.SHOW_ELECTRIC_FIELD_STIMULI,
            SchemaKey.FALSE_MESSAGE: "Electric field stimuli are not supported for this circuit.",
        },
    }

    title: ClassVar[str] = "Spatially Uniform Electric Field (Fixed Amplitude and Direction)"

    _module: str = "spatially_uniform_e_field"
    _input_type: str = "extracellular_stimulation"

    neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set",
        description="Neuron set to which the stimulus is applied.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: NeuronSetReference.__name__,
            SchemaKey.SUPPORTS_VIRTUAL: False,
        },
    )

    duration: (
        Annotated[NonNegativeFloat, Field(le=_MAX_SIMULATION_LENGTH_MILLISECONDS)]
        | list[Annotated[NonNegativeFloat, Field(le=_MAX_SIMULATION_LENGTH_MILLISECONDS)]]
    ) = Field(
        default=_DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
        title="Duration",
        description="Time in milliseconds (ms) for how long the main stimulus is activated. "
        + _RAMP_QAULIFIER_DESCRIPTION,
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    ramp_up_duration: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.0,
        description=(
            "Time over which the field linearly ramps up from zero to full amplitude, "
            "in milliseconds (ms). " + _RAMP_QAULIFIER_DESCRIPTION
        ),
        title="Ramp Up (Duration)",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    ramp_down_duration: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.0,
        description=(
            "Time over which the field linearly ramps down from full amplitude to zero, "
            "in milliseconds (ms). " + _RAMP_QAULIFIER_DESCRIPTION
        ),
        title="Ramp Down (Duration)",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    E_x: float | list[float] = Field(
        default=0.1,
        description="Amplitude of the electric field in the x-direction, in V/m. May be negative",
        title="X amplitude",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.VOLTS_PER_METER,
        },
    )

    E_y: float | list[float] = Field(
        default=0.1,
        description="Amplitude of the electric field in the y-direction, in V/m. May be negative",
        title="Y amplitude",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.VOLTS_PER_METER,
        },
    )

    E_z: float | list[float] = Field(
        default=0.1,
        description="Amplitude of the electric field in the z-direction, in V/m. May be negative",
        title="Z amplitude",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.VOLTS_PER_METER,
        },
    )

    _frequency: float = PrivateAttr(0.0)
    _phase_degrees: float = PrivateAttr(0.0)

    def _single_timestamp_stimulus_config(self, offset_timestamp: NonNegativeFloat) -> dict:
        stim_dict = {
            "delay": offset_timestamp,
            "duration": self.duration,
            "module": self._module,
            "input_type": self._input_type,
            "node_set": resolve_neuron_set_ref_to_node_set(self.neuron_set, self._default_node_set),
            "ramp_up_duration": self.ramp_up_duration,
            "ramp_down_duration": self.ramp_down_duration,
            "fields": [
                {
                    "Ex": self.E_x,
                    "Ey": self.E_y,
                    "Ez": self.E_z,
                    "frequency": self._frequency,
                    "phase": np.deg2rad(self._phase_degrees),
                }
            ],
        }
        return stim_dict


class TemporallyCosineSpatiallyUniformElectricFieldStimulus(SpatiallyUniformElectricFieldStimulus):
    """A spatially uniform electric field of fixed direction and time-varying magnitude.

    The stimulus is applied to all compartments of the selected Neuron Set.
    Neurons must be in a biophysical population.
    Stimulus magnitude varies cosinusoidally between zero and a maximum magnitude.
    The direction and maximum magnitude of the field are determined by the E_x, E_y, and E_z
    parameters.
    """

    title: ClassVar[str] = "Temporally Cosine Spatially Uniform Electric Field"

    frequency: (
        Annotated[
            NonNegativeFloat,
            Field(
                lt=_MAX_EFIELD_FREQUENCY_HZ,
            ),
        ]
        | Annotated[
            list[
                Annotated[
                    NonNegativeFloat,
                    Field(
                        lt=_MAX_EFIELD_FREQUENCY_HZ,
                    ),
                ]
            ],
            Field(min_length=1),
        ]
    ) = Field(
        default=0.0,
        description=(
            "Frequency of the cosinusoid, in Hz. Must be non-negative. If not provided, "
            "assumed to be 0. In this case, a time-invariant field with amplitude [Ex, Ey, Ez] "
            "is applied, unless ramp_up_duration or ramp_down_duration is specified, "
            "in which case the field will increase/decrease linearly "
            "with time during the ramp periods, and will "
            "be constant during the remainder of the stimulation period. Note that the signal "
            "will be generated with the same time step as the simulation itself. Note that "
            "frequency should therefore be less than the Nyquist frequency of the simulation "
            "(i.e., 1/(2*dt))"
        ),
        title="Frequency",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.HERTZ,
        },
    )

    phase_degrees: float | list[float] = Field(
        default=0.0,
        description="Phase of the cosinusoid, in degrees.",
        title="Phase",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.DEGREES,
        },
    )

    # Redefine E_x, E_y, and E_z with different names and descriptions

    E_x: float | list[float] = Field(
        default=0.1,
        description="Peak amplitude of the cosinusoid in the x-direction, in V/m. May be negative",
        title="X peak amplitude",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.VOLTS_PER_METER,
        },
    )

    E_y: float | list[float] = Field(
        default=0.1,
        description="Peak amplitude of the cosinusoid in the y-direction, in V/m. May be negative",
        title="Y peak amplitude",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.VOLTS_PER_METER,
        },
    )

    E_z: float | list[float] = Field(
        default=0.1,
        description="Peak amplitude of the cosinusoid in the z-direction, in V/m. May be negative",
        title="Z peak amplitude",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.VOLTS_PER_METER,
        },
    )

    @model_validator(mode="after")
    def _set_private_vars(self) -> Self:
        self._frequency = self.frequency
        self._phase_degrees = self.phase_degrees
        return self
