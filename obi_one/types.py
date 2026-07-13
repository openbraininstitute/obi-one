"""Module with shared types."""

import os
from enum import StrEnum, auto

StrOrPath = str | os.PathLike[str]


class SimulationBackend(StrEnum):
    bluecellulab = auto()
    neurodamus = auto()


class TaskType(StrEnum):
    """Task type identifiers."""

    # Task types supported for job submission (via the launch-system)
    circuit_extraction = auto()
    circuit_simulation = auto()
    circuit_simulation_inait_machine = auto()
    circuit_simulation_neuron = auto()
    circuit_simulation_neurodamus_cluster = auto()
    circuit_simulation_brian2_machine = auto()
    em_synapse_mapping = auto()
    efeature_extraction = auto()
    emodel_optimization = auto()
    emodel_export_and_validation = auto()
    extracellular_recording_weights_calculation = auto()
    ion_channel_model_simulation_execution = auto()
    mesh_lod_generation = auto()
    morphology_skeletonization = auto()

    # Task types supported for local-only execution (via scan generation / direct dispatch)
    basic_connectivity_plots = auto()
    brian2_circuit_simulation = auto()
    connectivity_matrix_extraction = auto()
    contribute_morphology = auto()
    electrophysiology_metrics = auto()
    folder_compression = auto()
    ion_channel_fitting = auto()
    ion_channel_model_simulation = auto()
    learning_engine_circuit_simulation = auto()
    me_model_simulation = auto()
    me_model_with_synapses_circuit_simulation = auto()
    morphology_containerization = auto()
    morphology_decontainerization = auto()
    morphology_locations = auto()
    morphology_metrics = auto()
