from typing import Annotated, ClassVar, Self

import numpy as np
from pydantic import ConfigDict, Field, NonNegativeFloat, PrivateAttr, model_validator

from obi_one.scientific.library.constants import (
    _DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
    _MAX_SIMULATION_LENGTH_MILLISECONDS,
)
from obi_one.scientific.unions.unions_timestamps import (
    resolve_timestamps_ref_to_timestamps_block,
)

from .stimulus import Stimulus


class SpatiallyUniformElectricFieldStimulus(Stimulus):
    """A uniform electric field stimulus applied to all compartments of biophysical neurons."""

    model_config = ConfigDict(
        json_schema_extra={
            "entity_property_requirement": {"scale": ["small_microcircuit"]},
            "entity_property_unfulfilled_message": "This stimulus is currently only "
            "supported for microcircuits.",
        }
    )

    title: ClassVar[str] = "Uniform Electric Field"

    _module: str = "spatially_uniform_e_field"
    _input_type: str = "extracellular_stimulation"

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

    E_x: float | list[float] = Field(
        default=0.1,
        description="Amplitude of the cosinusoid in the x-direction, in V/m. May be negative",
        title="Amplitude in x-direction.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "V/m",
        },
    )

    E_y: float | list[float] = Field(
        default=0.1,
        description="Amplitude of the cosinusoid in the y-direction, in V/m. May be negative",
        title="Amplitude in y-direction.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "V/m",
        },
    )

    E_z: float | list[float] = Field(
        default=0.1,
        description="Amplitude of the cosinusoid in the z-direction, in V/m. May be negative",
        title="Amplitude in z-direction.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "V/m",
        },
    )

    ramp_up_time: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.0,
        description="Time over which the field linearly ramps up from zero to full amplitude, \
            in milliseconds (ms).",
        title="Ramp Up Time",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "ms",
        },
    )

    ramp_down_time: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.0,
        description="Time over which the field linearly ramps down from full amplitude to zero, \
            in milliseconds (ms).",
        title="Ramp Down Time",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "ms",
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
                "delay": timestamp + self.timestamp_offset,
                "duration": self.duration,
                "module": self._module,
                "input_type": self._input_type,
                "ramp_up_time": self.ramp_up_time,
                "ramp_down_time": self.ramp_down_time,
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


class CosinusoidalSpatiallyUniformElectricFieldStimulus(SpatiallyUniformElectricFieldStimulus):
    frequency: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.0,
        description="Frequency of the cosinusoid, in Hz. Must be non-negative. If not provided, \
            assumed to be 0. In this case, a time-invariant field with amplitude [Ex, Ey, Ez] \
            is applied, unless ramp_up_time or ramp_down_time is specified, in which case the \
            field will increase/decrease linearly with time during the ramp periods, and will \
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
        title="Peak amplitude in x-direction.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "V/m",
        },
    )

    E_y: float | list[float] = Field(
        default=0.1,
        description="Peak amplitude of the cosinusoid in the y-direction, in V/m. May be negative",
        title="Peak amplitude in y-direction.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "V/m",
        },
    )

    E_z: float | list[float] = Field(
        default=0.1,
        description="Peak amplitude of the cosinusoid in the z-direction, in V/m. May be negative",
        title="Peak amplitude in z-direction.",
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
