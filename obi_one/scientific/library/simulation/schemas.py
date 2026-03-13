from pathlib import Path
from uuid import UUID

from pydantic import BaseModel


class SimulationParameters(BaseModel):
    number_of_cells: int
    stop_time: float
    config_file: Path
    libnrnmech_path: Path


class SimulationResults(BaseModel):
    spike_report_file: Path
    voltage_report_files: list[Path]


class SimulationMetadata(BaseModel):
    simulation_id: UUID
