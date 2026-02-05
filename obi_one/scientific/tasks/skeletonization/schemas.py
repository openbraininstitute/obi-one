from pathlib import Path

from entitysdk import models
from pydantic import BaseModel


class WorkDir(BaseModel):
    inputs: Path
    outputs: Path


class Metadata(BaseModel):
    cell_morphology_name: str
    cell_morphology_description: str
    cell_morphology_protocol_name: str
    cell_morphology_protocol_description: str
    subject: models.Subject
    brain_region: models.BrainRegion
    em_dense_reconstruction_dataset: models.EMDenseReconstructionDataset


class ProcessParameters(BaseModel):
    mesh_path: Path
    segment_spines: bool
    neuron_voxel_size: float
    spines_voxel_size: float


class SkeletonizationInputs(BaseModel):
    metadata: Metadata
    parameters: ProcessParameters


class SkeletonizationOutputs(BaseModel):
    h5_morphology_file: Path
    swc_morphology_file: Path
    asc_morphology_file: Path
    h5_combined_morphology_file: Path
