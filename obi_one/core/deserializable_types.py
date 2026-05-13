"""Explicit mapping of type names to their fully qualified class paths.

Used by core/deserialize.py to resolve the concrete class for a given
'type' field in serialized JSON without importing all scientific modules
eagerly. All deserializable types must have an entry in this dictionary.
"""

# ruff: noqa: E501 — long lines are unavoidable in a path mapping dict

from importlib import import_module

TYPE_MAP: dict[str, str] = {
    # Core types
    "Block": "obi_one.core.block.Block",
    "BlockReference": "obi_one.core.block_reference.BlockReference",
    "Info": "obi_one.core.info.Info",
    "NamedPath": "obi_one.core.path.NamedPath",
    "NamedTuple": "obi_one.core.tuple.NamedTuple",
    "ScanConfig": "obi_one.core.scan_config.ScanConfig",
    "GridScanGenerationTask": "obi_one.core.scan_generation.GridScanGenerationTask",
    "CoupledScanGenerationTask": "obi_one.core.scan_generation.CoupledScanGenerationTask",
    # Scan configs and single configs
    "BasicConnectivityPlotsScanConfig": "obi_one.scientific.tasks.basic_connectivity_plots.BasicConnectivityPlotsScanConfig",
    "BasicConnectivityPlotsSingleConfig": "obi_one.scientific.tasks.basic_connectivity_plots.BasicConnectivityPlotsSingleConfig",
    "CircuitExtractionScanConfig": "obi_one.scientific.tasks.circuit_extraction.CircuitExtractionScanConfig",
    "CircuitExtractionSingleConfig": "obi_one.scientific.tasks.circuit_extraction.CircuitExtractionSingleConfig",
    "CircuitSimulationScanConfig": "obi_one.scientific.tasks.generate_simulations.config.circuit.CircuitSimulationScanConfig",
    "CircuitSimulationSingleConfig": "obi_one.scientific.tasks.generate_simulations.config.circuit.CircuitSimulationSingleConfig",
    "ConnectivityMatrixExtractionScanConfig": "obi_one.scientific.tasks.connectivity_matrix_extraction.ConnectivityMatrixExtractionScanConfig",
    "ConnectivityMatrixExtractionSingleConfig": "obi_one.scientific.tasks.connectivity_matrix_extraction.ConnectivityMatrixExtractionSingleConfig",
    "ContributeMorphologyScanConfig": "obi_one.scientific.tasks.contribute.ContributeMorphologyScanConfig",
    "ContributeMorphologySingleConfig": "obi_one.scientific.tasks.contribute.ContributeMorphologySingleConfig",
    "ContributeSubjectScanConfig": "obi_one.scientific.tasks.contribute.ContributeSubjectScanConfig",
    "ContributeSubjectSingleConfig": "obi_one.scientific.tasks.contribute.ContributeSubjectSingleConfig",
    "ElectrophysiologyMetricsScanConfig": "obi_one.scientific.tasks.ephys_extraction.ElectrophysiologyMetricsScanConfig",
    "ElectrophysiologyMetricsSingleConfig": "obi_one.scientific.tasks.ephys_extraction.ElectrophysiologyMetricsSingleConfig",
    "EMSynapseMappingScanConfig": "obi_one.scientific.tasks.em_synapse_mapping.config.EMSynapseMappingScanConfig",
    "EMSynapseMappingSingleConfig": "obi_one.scientific.tasks.em_synapse_mapping.config.EMSynapseMappingSingleConfig",
    "FolderCompressionScanConfig": "obi_one.scientific.tasks.folder_compression.FolderCompressionScanConfig",
    "FolderCompressionSingleConfig": "obi_one.scientific.tasks.folder_compression.FolderCompressionSingleConfig",
    "IonChannelFittingScanConfig": "obi_one.scientific.tasks.ion_channel_modeling.IonChannelFittingScanConfig",
    "IonChannelFittingSingleConfig": "obi_one.scientific.tasks.ion_channel_modeling.IonChannelFittingSingleConfig",
    "IonChannelModelSimulationScanConfig": "obi_one.scientific.tasks.generate_simulations.config.ion_channel_models.IonChannelModelSimulationScanConfig",
    "IonChannelModelSimulationSingleConfig": "obi_one.scientific.tasks.generate_simulations.config.ion_channel_models.IonChannelModelSimulationSingleConfig",
    "MEModelSimulationScanConfig": "obi_one.scientific.tasks.generate_simulations.config.me_model.MEModelSimulationScanConfig",
    "MEModelSimulationSingleConfig": "obi_one.scientific.tasks.generate_simulations.config.me_model.MEModelSimulationSingleConfig",
    "MEModelWithSynapsesCircuitSimulationScanConfig": "obi_one.scientific.tasks.generate_simulations.config.me_model_with_synapses.MEModelWithSynapsesCircuitSimulationScanConfig",
    "MEModelWithSynapsesCircuitSimulationSingleConfig": "obi_one.scientific.tasks.generate_simulations.config.me_model_with_synapses.MEModelWithSynapsesCircuitSimulationSingleConfig",
    "MorphologyContainerizationScanConfig": "obi_one.scientific.tasks.morphology_containerization.MorphologyContainerizationScanConfig",
    "MorphologyContainerizationSingleConfig": "obi_one.scientific.tasks.morphology_containerization.MorphologyContainerizationSingleConfig",
    "MorphologyDecontainerizationScanConfig": "obi_one.scientific.tasks.morphology_decontainerization.MorphologyDecontainerizationScanConfig",
    "MorphologyDecontainerizationSingleConfig": "obi_one.scientific.tasks.morphology_decontainerization.MorphologyDecontainerizationSingleConfig",
    "MorphologyLocationsScanConfig": "obi_one.scientific.tasks.morphology_locations.MorphologyLocationsScanConfig",
    "MorphologyLocationsSingleConfig": "obi_one.scientific.tasks.morphology_locations.MorphologyLocationsSingleConfig",
    "MorphologyMetricsScanConfig": "obi_one.scientific.tasks.morphology_metrics.MorphologyMetricsScanConfig",
    "MorphologyMetricsSingleConfig": "obi_one.scientific.tasks.morphology_metrics.MorphologyMetricsSingleConfig",
    "SkeletonizationScanConfig": "obi_one.scientific.tasks.skeletonization.SkeletonizationScanConfig",
    "SkeletonizationSingleConfig": "obi_one.scientific.tasks.skeletonization.SkeletonizationSingleConfig",
    # __init__.py aliases
    "GridScan": "obi_one.GridScan",
    "CoupledScan": "obi_one.CoupledScan",
    "SimulationsForm": "obi_one.scientific.unions.aliases.SimulationsForm",
}


def load_class(type_name: str) -> type:
    """Resolve a type name to its class using TYPE_MAP and lazy import."""
    path = TYPE_MAP[type_name]
    module_path, class_name = path.rsplit(".", 1)
    module = import_module(module_path)
    return getattr(module, class_name)
