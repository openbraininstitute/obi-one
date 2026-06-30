"""Explicit mapping of type names to their module paths.

Used by core/deserialize.py to resolve the concrete class for a given
'type' field in serialized JSON without importing all scientific modules
eagerly. All deserializable types must have an entry in this dictionary.

The key is the class name (matching the 'type' field in JSON), and the
value is the module where that class is defined.
"""

# ruff: noqa: E501 — long lines are unavoidable in a path mapping dict

from importlib import import_module

TYPE_MAP: dict[str, str] = {
    # Core types
    "Block": "obi_one.core.block",
    "BlockReference": "obi_one.core.block_reference",
    "CoupledScanGenerationTask": "obi_one.core.scan_generation",
    "GridScanGenerationTask": "obi_one.core.scan_generation",
    "Info": "obi_one.core.info",
    "NamedPath": "obi_one.core.path",
    "NamedTuple": "obi_one.core.tuple",
    "ScanConfig": "obi_one.core.scan_config",
    # Scan configs and single configs
    "AINDEPhysDispatchScanConfig": "obi_one.scientific.tasks.aind_ephys._01_dispatch.config",
    "AINDEPhysDispatchSingleConfig": "obi_one.scientific.tasks.aind_ephys._01_dispatch.config",
    "AINDEPhysPreprocessingScanConfig": "obi_one.scientific.tasks.aind_ephys._02_preprocessing.config",
    "AINDEPhysPreprocessingSingleConfig": "obi_one.scientific.tasks.aind_ephys._02_preprocessing.config",
    "AINDEPhysSpikesortKilosort4ScanConfig": "obi_one.scientific.tasks.aind_ephys._03_kilosort4.config",
    "AINDEPhysSpikesortKilosort4SingleConfig": "obi_one.scientific.tasks.aind_ephys._03_kilosort4.config",
    "AINDEPhysPostprocessingScanConfig": "obi_one.scientific.tasks.aind_ephys._04_postprocessing.config",
    "AINDEPhysPostprocessingSingleConfig": "obi_one.scientific.tasks.aind_ephys._04_postprocessing.config",
    "AINDEPhysCurationScanConfig": "obi_one.scientific.tasks.aind_ephys._05_curation.config",
    "AINDEPhysCurationSingleConfig": "obi_one.scientific.tasks.aind_ephys._05_curation.config",
    "AINDEPhysVisualizationScanConfig": "obi_one.scientific.tasks.aind_ephys._06_visualization.config",
    "AINDEPhysVisualizationSingleConfig": "obi_one.scientific.tasks.aind_ephys._06_visualization.config",
    "AINDEPhysResultsCollectorScanConfig": "obi_one.scientific.tasks.aind_ephys._07_results_collector.config",
    "AINDEPhysResultsCollectorSingleConfig": "obi_one.scientific.tasks.aind_ephys._07_results_collector.config",
    "AINDEPhysProcessingQCScanConfig": "obi_one.scientific.tasks.aind_ephys._08_processing_qc.config",
    "AINDEPhysProcessingQCSingleConfig": "obi_one.scientific.tasks.aind_ephys._08_processing_qc.config",
    "AINDEPhysQCCollectorScanConfig": "obi_one.scientific.tasks.aind_ephys._09_qc_collector.config",
    "AINDEPhysQCCollectorSingleConfig": "obi_one.scientific.tasks.aind_ephys._09_qc_collector.config",
    "AINDEcephysNWBScanConfig": "obi_one.scientific.tasks.aind_ephys._10_ecephys_nwb.config",
    "AINDEcephysNWBSingleConfig": "obi_one.scientific.tasks.aind_ephys._10_ecephys_nwb.config",
    "AINDUnitsNWBScanConfig": "obi_one.scientific.tasks.aind_ephys._11_units_nwb.config",
    "AINDUnitsNWBSingleConfig": "obi_one.scientific.tasks.aind_ephys._11_units_nwb.config",
    "BasicConnectivityPlotsScanConfig": "obi_one.scientific.tasks.basic_connectivity_plots",
    "BasicConnectivityPlotsSingleConfig": "obi_one.scientific.tasks.basic_connectivity_plots",
    "CircuitExtractionScanConfig": "obi_one.scientific.tasks.circuit_extraction",
    "CircuitExtractionSingleConfig": "obi_one.scientific.tasks.circuit_extraction",
    "CircuitSimulationScanConfig": "obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit",
    "CircuitSimulationSingleConfig": "obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit",
    "ConnectivityMatrixExtractionScanConfig": "obi_one.scientific.tasks.connectivity_matrix_extraction",
    "ConnectivityMatrixExtractionSingleConfig": "obi_one.scientific.tasks.connectivity_matrix_extraction",
    "ContributeMorphologyScanConfig": "obi_one.scientific.tasks.contribute",
    "ContributeMorphologySingleConfig": "obi_one.scientific.tasks.contribute",
    "ContributeSubjectScanConfig": "obi_one.scientific.tasks.contribute",
    "ContributeSubjectSingleConfig": "obi_one.scientific.tasks.contribute",
    "CreateExtracellularRecordingArrayScanConfig": "obi_one.scientific.tasks.create_recording_array.create_recording_array",
    "CreateExtracellularRecordingArraySingleConfig": "obi_one.scientific.tasks.create_recording_array.create_recording_array",
    "ElectrophysiologyMetricsScanConfig": "obi_one.scientific.tasks.ephys_extraction",
    "ElectrophysiologyMetricsSingleConfig": "obi_one.scientific.tasks.ephys_extraction",
    "EMSynapseMappingScanConfig": "obi_one.scientific.tasks.em_synapse_mapping.config",
    "EMSynapseMappingSingleConfig": "obi_one.scientific.tasks.em_synapse_mapping.config",
    "FolderCompressionScanConfig": "obi_one.scientific.tasks.folder_compression",
    "FolderCompressionSingleConfig": "obi_one.scientific.tasks.folder_compression",
    "IonChannelFittingScanConfig": "obi_one.scientific.tasks.ion_channel_modeling",
    "IonChannelFittingSingleConfig": "obi_one.scientific.tasks.ion_channel_modeling",
    "IonChannelModelSimulationScanConfig": "obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_ion_channel_models",
    "IonChannelModelSimulationSingleConfig": "obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_ion_channel_models",
    "LearningEngineCircuitSimulationScanConfig": "obi_one.scientific.tasks.generate_simulations.config.learning_engine.le_circuit",
    "LearningEngineCircuitSimulationSingleConfig": "obi_one.scientific.tasks.generate_simulations.config.learning_engine.le_circuit",
    "MEModelSimulationScanConfig": "obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model",
    "MEModelSimulationSingleConfig": "obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model",
    "MEModelWithSynapsesCircuitSimulationScanConfig": "obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model_with_synapses",
    "MEModelWithSynapsesCircuitSimulationSingleConfig": "obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model_with_synapses",
    "MorphologyContainerizationScanConfig": "obi_one.scientific.tasks.morphology_containerization",
    "MorphologyContainerizationSingleConfig": "obi_one.scientific.tasks.morphology_containerization",
    "MorphologyDecontainerizationScanConfig": "obi_one.scientific.tasks.morphology_decontainerization",
    "MorphologyDecontainerizationSingleConfig": "obi_one.scientific.tasks.morphology_decontainerization",
    "MorphologyLocationsScanConfig": "obi_one.scientific.tasks.morphology_locations",
    "MorphologyLocationsSingleConfig": "obi_one.scientific.tasks.morphology_locations",
    "MorphologyMetricsScanConfig": "obi_one.scientific.tasks.morphology_metrics",
    "MorphologyMetricsSingleConfig": "obi_one.scientific.tasks.morphology_metrics",
    "SkeletonizationScanConfig": "obi_one.scientific.tasks.skeletonization",
    "SkeletonizationSingleConfig": "obi_one.scientific.tasks.skeletonization",
    # __init__.py aliases (class is re-exported under this name)
    "CoupledScan": "obi_one",
    "GridScan": "obi_one",
    "SimulationsForm": "obi_one.scientific.unions.aliases",
}


def load_class(type_name: str) -> type:
    """Resolve a type name to its class using TYPE_MAP and lazy import."""
    module_path = TYPE_MAP[type_name]
    module = import_module(module_path)
    return getattr(module, type_name)
