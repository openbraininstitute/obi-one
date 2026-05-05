"""Data schemas used by simulation execution and registration."""

from pathlib import Path
from uuid import UUID

from pydantic import BaseModel


class SimulationParameters(BaseModel):
    """Inputs required to execute a simulation run."""

    number_of_cells: int
    stop_time: float
    config_file: Path
    libnrnmech_path: Path


class SimulationResults(BaseModel):
    """Output artifact paths produced by a simulation run."""

    spike_report_file: Path
    voltage_report_files: list[Path]


class SimulationMetadata(BaseModel):
    """Identifiers needed to register simulation outputs."""

    simulation_id: UUID
