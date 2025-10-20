from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
from obi_one.core.block_reference import BlockReference
from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.core.path import NamedPath
from obi_one.core.run_tasks import (
    run_task_for_single_config,
    run_task_for_single_configs,
    run_tasks_for_generated_scan,
)
from obi_one.core.scan_config import ScanConfig
from obi_one.core.serialization import (
    deserialize_obi_object_from_json_data,
    deserialize_obi_object_from_json_file,
)
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.core.tuple import NamedTuple

__all__ = [
    "AfferentSynapsesBlock",
    "AllNeurons",
    "BasicConnectivityPlotsScanConfig",
    "BasicConnectivityPlotsSingleConfig",
    "BasicConnectivityPlotsTask",
    "Block",
    "BlockReference",
    "CellMorphologyFromID",
    "Circuit",
    "CircuitExtractionScanConfig",
    "CircuitExtractionSingleConfig",
    "CircuitExtractionTask",
    "CircuitFromID",
    "CircuitSimulationScanConfig",
    "CircuitSimulationSingleConfig",
    "ClusteredGroupedMorphologyLocations",
    "ClusteredMorphologyLocations",
    "ClusteredPDSynapsesByCount",
    "ClusteredPDSynapsesByMaxDistance",
    "ClusteredPathDistanceMorphologyLocations",
    "ClusteredSynapsesByCount",
    "ClusteredSynapsesByMaxDistance",
    "CombinedNeuronSet",
    "ConnectivityMatrixExtractionScanConfig",
    "ConnectivityMatrixExtractionSingleConfig",
    "ConnectivityMatrixExtractionTask",
    "ConstantCurrentClampSomaticStimulus",
    "ContributeMorphologyScanConfig",
    "ContributeMorphologySingleConfig",
    "ContributeSubjectScanConfig",
    "ContributeSubjectSingleConfig",
    "CoupledScan",
    "CoupledScanGenerationTask",
    "ElectrophysiologyMetricsScanConfig",
    "ElectrophysiologyMetricsSingleConfig",
    "ElectrophysiologyMetricsTask",
    "EntityFromID",
    "ExcitatoryNeurons",
    "ExtracellularLocations",
    "ExtracellularLocationsUnion",
    "FloatRange",
    "FolderCompressionScanConfig",
    "FolderCompressionSingleConfig",
    "FolderCompressionTask",
    "FullySynchronousSpikeStimulus",
    "GenerateSimulationTask",
    "GridScan",
    "GridScanGenerationTask",
    "HyperpolarizingCurrentClampSomaticStimulus",
    "IDNeuronSet",
    "Info",
    "InhibitoryNeurons",
    "IntRange",
    "IonChannelFittingScanConfig",
    "IonChannelFittingSingleConfig",
    "IonChannelFittingTask",
    "LinearCurrentClampSomaticStimulus",
    "LoadAssetMethod",
    "MEModelCircuit",
    "MEModelFromID",
    "MEModelSimulationScanConfig",
    "MEModelSimulationSingleConfig",
    "MorphologyContainerizationScanConfig",
    "MorphologyContainerizationSingleConfig",
    "MorphologyContainerizationTask",
    "MorphologyDecontainerizationScanConfig",
    "MorphologyDecontainerizationSingleConfig",
    "MorphologyDecontainerizationTask",
    "MorphologyLocationsScanConfig",
    "MorphologyLocationsSingleConfig",
    "MorphologyLocationsTask",
    "MorphologyMetricsOutput",
    "MorphologyMetricsScanConfig",
    "MorphologyMetricsSingleConfig",
    "MorphologyMetricsTask",
    "MultiPulseCurrentClampSomaticStimulus",
    "NamedPath",
    "NamedTuple",
    "NeuronPropertyFilter",
    "NeuronSet",
    "NeuronSetReference",
    "NeuronSetUnion",
    "NonNegativeFloatRange",
    "NonNegativeIntRange",
    "NormallyDistributedCurrentClampSomaticStimulus",
    "OBIBaseModel",
    "OBIONEError",
    "PairMotifNeuronSet",
    "PathDistanceConstrainedFractionOfSynapses",
    "PathDistanceConstrainedNumberOfSynapses",
    "PathDistanceMorphologyLocations",
    "PathDistanceWeightedFractionOfSynapses",
    "PathDistanceWeightedNumberOfSynapses",
    "PoissonSpikeStimulus",
    "PositiveFloatRange",
    "PositiveIntRange",
    "PredefinedNeuronSet",
    "PropertyNeuronSet",
    "RandomGroupedMorphologyLocations",
    "RandomMorphologyLocations",
    "RandomlySelectedFractionOfSynapses",
    "RandomlySelectedNumberOfSynapses",
    "Recording",
    "RecordingReference",
    "RecordingUnion",
    "RegularTimestamps",
    "RelativeConstantCurrentClampSomaticStimulus",
    "RelativeLinearCurrentClampSomaticStimulus",
    "RelativeNormallyDistributedCurrentClampSomaticStimulus",
    "ScaleAcetylcholineUSESynapticManipulation",
    "ScanConfig",
    "ScanConfig",
    "ScanConfigsUnion",
    "ScanGenerationTask",
    "SimplexMembershipBasedNeuronSet",
    "SimplexNeuronSet",
    "Simulation",
    "SimulationNeuronSetUnion",
    "SimulationsForm",
    "SingleConfigMixin",
    "SingleConfigMixin",
    "SingleTimestamp",
    "SinusoidalCurrentClampSomaticStimulus",
    "SomaVoltageRecording",
    "StimulusReference",
    "StimulusUnion",
    "SubthresholdCurrentClampSomaticStimulus",
    "SynapseSetUnion",
    "SynapticMgManipulation",
    "Task",
    "TasksUnion",
    "TimeWindowSomaVoltageRecording",
    "Timestamps",
    "TimestampsReference",
    "TimestampsUnion",
    "VolumetricCountNeuronSet",
    "VolumetricRadiusNeuronSet",
    "XYZExtracellularLocations",
    "add_node_set_to_circuit",
    "deserialize_obi_object_from_json_data",
    "deserialize_obi_object_from_json_file",
    "get_configs_task_type",
    "nbS1POmInputs",
    "nbS1VPMInputs",
    "rCA1CA3Inputs",
    "run_task_for_single_config",
    "run_task_for_single_configs",
    "run_tasks_for_generated_scan",
    "write_circuit_node_set_file",
]

from obi_one.core.entity_from_id import EntityFromID, LoadAssetMethod
from obi_one.core.parametric_multi_values import (
    FloatRange,
    IntRange,
    NonNegativeFloatRange,
    NonNegativeIntRange,
    PositiveFloatRange,
    PositiveIntRange,
)
from obi_one.core.scan_generation import (
    CoupledScanGenerationTask,
    GridScanGenerationTask,
    ScanGenerationTask,
)
from obi_one.scientific.blocks.afferent_synapses import (
    AfferentSynapsesBlock,
    ClusteredPDSynapsesByCount,
    ClusteredPDSynapsesByMaxDistance,
    ClusteredSynapsesByCount,
    ClusteredSynapsesByMaxDistance,
    PathDistanceConstrainedFractionOfSynapses,
    PathDistanceConstrainedNumberOfSynapses,
    PathDistanceWeightedFractionOfSynapses,
    PathDistanceWeightedNumberOfSynapses,
    RandomlySelectedFractionOfSynapses,
    RandomlySelectedNumberOfSynapses,
)
from obi_one.scientific.blocks.extracellular_locations import (
    ExtracellularLocations,
    XYZExtracellularLocations,
)
from obi_one.scientific.blocks.morphology_locations.clustered import (
    ClusteredGroupedMorphologyLocations,
    ClusteredMorphologyLocations,
    ClusteredPathDistanceMorphologyLocations,
)
from obi_one.scientific.blocks.morphology_locations.path_distance import (
    PathDistanceMorphologyLocations,
)
from obi_one.scientific.blocks.morphology_locations.random import (
    RandomGroupedMorphologyLocations,
    RandomMorphologyLocations,
)
from obi_one.scientific.blocks.neuron_sets.base import NeuronSet
from obi_one.scientific.blocks.neuron_sets.combined import CombinedNeuronSet
from obi_one.scientific.blocks.neuron_sets.id import IDNeuronSet
from obi_one.scientific.blocks.neuron_sets.pair import PairMotifNeuronSet
from obi_one.scientific.blocks.neuron_sets.predefined import PredefinedNeuronSet
from obi_one.scientific.blocks.neuron_sets.property import NeuronPropertyFilter, PropertyNeuronSet
from obi_one.scientific.blocks.neuron_sets.simplex import (
    SimplexMembershipBasedNeuronSet,
    SimplexNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets.specific import (
    AllNeurons,
    ExcitatoryNeurons,
    InhibitoryNeurons,
    nbS1POmInputs,
    nbS1VPMInputs,
    rCA1CA3Inputs,
)
from obi_one.scientific.blocks.neuron_sets.volumetric import (
    VolumetricCountNeuronSet,
    VolumetricRadiusNeuronSet,
)
from obi_one.scientific.blocks.recording import (
    Recording,
    SomaVoltageRecording,
    TimeWindowSomaVoltageRecording,
)
from obi_one.scientific.blocks.stimulus import (
    ConstantCurrentClampSomaticStimulus,
    FullySynchronousSpikeStimulus,
    HyperpolarizingCurrentClampSomaticStimulus,
    LinearCurrentClampSomaticStimulus,
    MultiPulseCurrentClampSomaticStimulus,
    NormallyDistributedCurrentClampSomaticStimulus,
    PoissonSpikeStimulus,
    RelativeConstantCurrentClampSomaticStimulus,
    RelativeLinearCurrentClampSomaticStimulus,
    RelativeNormallyDistributedCurrentClampSomaticStimulus,
    SinusoidalCurrentClampSomaticStimulus,
    SubthresholdCurrentClampSomaticStimulus,
)
from obi_one.scientific.blocks.timestamps import RegularTimestamps, SingleTimestamp, Timestamps
from obi_one.scientific.from_id.cell_morphology_from_id import (
    CellMorphologyFromID,
)
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.memodel_circuit import MEModelCircuit
from obi_one.scientific.library.morphology_metrics import (
    MorphologyMetricsOutput,
)
from obi_one.scientific.library.sonata_circuit_helpers import (
    add_node_set_to_circuit,
    write_circuit_node_set_file,
)
from obi_one.scientific.tasks.basic_connectivity_plots import (
    BasicConnectivityPlotsScanConfig,
    BasicConnectivityPlotsSingleConfig,
    BasicConnectivityPlotsTask,
)
from obi_one.scientific.tasks.circuit_extraction import (
    CircuitExtractionScanConfig,
    CircuitExtractionSingleConfig,
    CircuitExtractionTask,
)
from obi_one.scientific.tasks.connectivity_matrix_extraction import (
    ConnectivityMatrixExtractionScanConfig,
    ConnectivityMatrixExtractionSingleConfig,
    ConnectivityMatrixExtractionTask,
)
from obi_one.scientific.tasks.contribute import (
    ContributeMorphologyScanConfig,
    ContributeMorphologySingleConfig,
    ContributeSubjectScanConfig,
    ContributeSubjectSingleConfig,
)
from obi_one.scientific.tasks.ephys_extraction import (
    ElectrophysiologyMetricsScanConfig,
    ElectrophysiologyMetricsSingleConfig,
    ElectrophysiologyMetricsTask,
)
from obi_one.scientific.tasks.folder_compression import (
    FolderCompressionScanConfig,
    FolderCompressionSingleConfig,
    FolderCompressionTask,
)
from obi_one.scientific.tasks.generate_simulation_configs import (
    CircuitSimulationScanConfig,
    CircuitSimulationSingleConfig,
    MEModelSimulationScanConfig,
    MEModelSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulation_task import (
    GenerateSimulationTask,
)
from obi_one.scientific.tasks.ion_channel_modeling import (
    IonChannelFittingScanConfig,
    IonChannelFittingSingleConfig,
    IonChannelFittingTask,
)
from obi_one.scientific.tasks.morphology_containerization import (
    MorphologyContainerizationScanConfig,
    MorphologyContainerizationSingleConfig,
    MorphologyContainerizationTask,
)
from obi_one.scientific.tasks.morphology_decontainerization import (
    MorphologyDecontainerizationScanConfig,
    MorphologyDecontainerizationSingleConfig,
    MorphologyDecontainerizationTask,
)
from obi_one.scientific.tasks.morphology_locations import (
    MorphologyLocationsScanConfig,
    MorphologyLocationsSingleConfig,
    MorphologyLocationsTask,
)
from obi_one.scientific.tasks.morphology_metrics import (
    MorphologyMetricsScanConfig,
    MorphologyMetricsSingleConfig,
    MorphologyMetricsTask,
)
from obi_one.scientific.unions.aliases import Simulation, SimulationsForm
from obi_one.scientific.unions.config_task_map import get_configs_task_type
from obi_one.scientific.unions.unions_extracellular_locations import (
    ExtracellularLocationsUnion,
)
from obi_one.scientific.unions.unions_manipulations import (
    ScaleAcetylcholineUSESynapticManipulation,
    SynapticMgManipulation,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    NeuronSetUnion,
    SimulationNeuronSetUnion,
)
from obi_one.scientific.unions.unions_recordings import RecordingReference, RecordingUnion
from obi_one.scientific.unions.unions_scan_configs import ScanConfigsUnion
from obi_one.scientific.unions.unions_stimuli import StimulusReference, StimulusUnion
from obi_one.scientific.unions.unions_synapse_set import SynapseSetUnion
from obi_one.scientific.unions.unions_tasks import TasksUnion
from obi_one.scientific.unions.unions_timestamps import TimestampsReference, TimestampsUnion

LAB_ID_STAGING_TEST = "e6030ed8-a589-4be2-80a6-f975406eb1f6"
PROJECT_ID_STAGING_TEST = "2720f785-a3a2-4472-969d-19a53891c817"


class GridScan(GridScanGenerationTask):
    pass


class CoupledScan(CoupledScanGenerationTask):
    pass
