from typing import Annotated, ClassVar, Self

import numpy as np
from pydantic import Field, NonNegativeFloat, PrivateAttr, model_validator

from obi_one.scientific.library.constants import (
    _DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
    _MAX_EFIELD_FREQUENCY_HZ,
    _MAX_SIMULATION_LENGTH_MILLISECONDS,
)
from obi_one.scientific.library.entity_property_types import (
    CircuitSimulationUsabilityOption,
    EntityType,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    resolve_neuron_set_ref_to_node_set,
)
from obi_one.scientific.unions.unions_timestamps import (
    resolve_timestamps_ref_to_timestamps_block,
)

from .stimulus import ContinuousStimulus


class SpatiallyUniformElectricFieldStimulus(ContinuousStimulus):
    """A spatially uniform electric field of fixed magnitute and direction.

    The stimulus is applied to all compartments of the selected Neuron Set.
    Neurons must be in a biophysical population.
    """

    json_schema_extra_additions: ClassVar[dict] = {
        "block_usability_entity_dependent": True,
        "block_usability_entity_type": EntityType.CIRCUIT,
        "block_usability_property": CircuitSimulationUsabilityOption.SHOW_ELECTRIC_FIELD_STIMULI,
        "block_usability_false_message": "This stimulus is currently only supported for microcircuits.",
    }

    title: ClassVar[str] = "Spatially Uniform Electric Field (Fixed Amplitude and Direction)"

    _module: str = "spatially_uniform_e_field"
    _input_type: str = "extracellular_stimulation"

    neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set",
        description="Neuron set to which the stimulus is applied.",
        json_schema_extra={
            "ui_element": "reference",
            "reference_type": NeuronSetReference.__name__,
            "supports_virtual": False,
        },
    )

    duration: (
        Annotated[NonNegativeFloat, Field(le=_MAX_SIMULATION_LENGTH_MILLISECONDS)]
        | list[Annotated[NonNegativeFloat, Field(le=_MAX_SIMULATION_LENGTH_MILLISECONDS)]]
    ) = Field(
        default=_DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
        title="Duration",
        description="Time duration in milliseconds for how long input is activated.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "ms",
        },
    )

    ramp_up_duration: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.0,
        description="Time over which the field linearly ramps up from zero to full amplitude, \
            in milliseconds (ms).",
        title="Ramp Up (Duration)",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "ms",
        },
    )

    ramp_down_duration: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.0,
        description="Time over which the field linearly ramps down from full amplitude to zero, \
            in milliseconds (ms).",
        title="Ramp Down (Duration)",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "ms",
        },
    )

    E_x: float | list[float] = Field(
        default=0.1,
        description="Amplitude of the electric field in the x-direction, in V/m. May be negative",
        title="X amplitude",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "V/m",
        },
    )

    E_y: float | list[float] = Field(
        default=0.1,
        description="Amplitude of the electric field in the y-direction, in V/m. May be negative",
        title="Y amplitude",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "V/m",
        },
    )

    E_z: float | list[float] = Field(
        default=0.1,
        description="Amplitude of the electric field in the z-direction, in V/m. May be negative",
        title="Z amplitude",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "V/m",
        },
    )

    _frequency: float = PrivateAttr(0.0)
    _phase_degrees: float = PrivateAttr(0.0)

    def _generate_config(self) -> dict:
        sonata_config = {}

        timestamps_block = resolve_timestamps_ref_to_timestamps_block(
            self.timestamps, self._default_timestamps
        )

        for t_ind, timestamp in enumerate(timestamps_block.timestamps()):
            sonata_config[self.block_name + "_" + str(t_ind)] = {
                "module": self._module,
                "input_type": self._input_type,
                "node_set": resolve_neuron_set_ref_to_node_set(
                    self.neuron_set, self._default_node_set
                ),
                "delay": timestamp + self.timestamp_offset,
                "duration": self.duration,
                "ramp_up_duration": self.ramp_up_duration,
                "ramp_down_duration": self.ramp_down_duration,
                "fields": [
                    {
                        "E_x": self.E_x,
                        "E_y": self.E_y,
                        "E_z": self.E_z,
                        "frequency": self._frequency,
                        "phase": np.deg2rad(self._phase_degrees),
                    }
                ],
            }
        return sonata_config


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
                le=_MAX_EFIELD_FREQUENCY_HZ,
            ),
        ]
        | Annotated[
            list[
                Annotated[
                    NonNegativeFloat,
                    Field(
                        le=_MAX_EFIELD_FREQUENCY_HZ,
                    ),
                ]
            ],
            Field(min_length=1),
        ]
    ) = Field(
        default=0.0,
        description="Frequency of the cosinusoid, in Hz. Must be non-negative. If not provided, \
            assumed to be 0. In this case, a time-invariant field with amplitude [Ex, Ey, Ez] \
            is applied, unless ramp_up_duration or ramp_down_duration is specified,  \
            in which case the field will increase/decrease linearly \
            with time during the ramp periods, and will \
            be constant during the remaider of the stimulation period. Note that the signal \
            will be generated with the same time step as the simulation itself. Note that \
            frequency should therefore be less than the Nyquist frequency of the simulation \
            (i.e., 1/(2*dt))",
        title="Frequency",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "Hz",
        },
    )

    phase_degrees: float | list[float] = Field(
        default=0.0,
        description="Phase of the cosinusoid, in degrees.",
        title="Phase",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "°",
        },
    )

    # Redefine E_x, E_y, and E_z with different names and descriptions

    E_x: float | list[float] = Field(
        default=0.1,
        description="Peak amplitude of the cosinusoid in the x-direction, in V/m. May be negative",
        title="X peak amplitude",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "V/m",
        },
    )

    E_y: float | list[float] = Field(
        default=0.1,
        description="Peak amplitude of the cosinusoid in the y-direction, in V/m. May be negative",
        title="Y peak amplitude",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "V/m",
        },
    )

    E_z: float | list[float] = Field(
        default=0.1,
        description="Peak amplitude of the cosinusoid in the z-direction, in V/m. May be negative",
        title="Z peak amplitude",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "V/m",
        },
    )

    @model_validator(mode="after")
    def _set_private_vars(self) -> Self:
        self._frequency = self.frequency
        self._phase_degrees = self.phase_degrees
        return self
