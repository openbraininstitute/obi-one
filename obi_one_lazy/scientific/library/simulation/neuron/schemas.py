"""Data schemas used by simulation execution and registration."""

from pathlib import Path
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, FilePath


class NeuronMechanismBuild(BaseModel):
    libnrnmech_path: Annotated[FilePath, Field(description="Path to libnrnmech.so")]


class NeurodamusMechanismBuild(BaseModel):
    libnrnmech_path: Annotated[FilePath, Field(description="Path to libnrnmech.so")]
    libcorenrnmech_path: Annotated[FilePath, Field(description="Path to libcorenrnmech.so")]
    special_binary_path: Annotated[
        FilePath, Field(description="Path to compiled NEURON special binary")
    ]


type MechanismBuild = NeuronMechanismBuild | NeurodamusMechanismBuild


class SimulationParametersBase(BaseModel):
    """Inputs required to execute a simulation run."""

    number_of_cells: int
    stop_time: float
    config_file: Path


class BluecellulabSimulationParameters(SimulationParametersBase):
    mechanism_build: NeuronMechanismBuild


class NeurodamusSimulationParameters(SimulationParametersBase):
    mechanism_build: NeurodamusMechanismBuild


type SimulationParameters = BluecellulabSimulationParameters | NeurodamusSimulationParameters


class SimulationResults(BaseModel):
    """Output artifact paths produced by a simulation run."""

    spike_report_file: Path
    voltage_report_files: list[Path]


class SimulationMetadata(BaseModel):
    """Identifiers needed to register simulation outputs."""

    simulation_id: UUID
