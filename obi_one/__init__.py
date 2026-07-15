from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
from obi_one.core.block_reference import BlockReference
from obi_one.core.deserialize import (
    deserialize_obi_object_from_json_data,
    deserialize_obi_object_from_json_file,
)
from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.core.path import NamedPath
from obi_one.core.run_tasks import (
    run_task_for_single_config,
    run_task_for_single_config_asset,
    run_task_for_single_configs,
    run_tasks_for_generated_scan,
)
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.core.tuple import NamedTuple

__all__ = [
    "AfferentSynapsesBlock",
    "AllBiophysicalNeurons",
    "AllDistributionsReference",
    "AllDistributionsUnion",
    "AllNonVirtualNeurons",
    "AllPairsSynapticModelAssigner",
    "AllPointNeurons",
    "AllPopulationNeurons",
    "AllVirtualNeurons",
    "BasicConnectivityPlotsScanConfig",
    "BasicConnectivityPlotsSingleConfig",
    "BasicConnectivityPlotsTask",
    "BiophysicalCombinedNeuronSet",
    "BiophysicalNeuronSetReference",
    "BiophysicalPopulationIDNeuronSet",
    "BiophysicalPopulationNeuronSet",
    "BiophysicalPopulationPredefinedNeuronSet",
    "BiophysicalPopulationPropertyNeuronSet",
    "Block",
    "BlockReference",
    "Brian2CircuitSimulationScanConfig",
    "Brian2CircuitSimulationSingleConfig",
    "CellMorphologyFromID",
    "Circuit",
    "CircuitExtractionScanConfig",
    "CircuitExtractionSingleConfig",
    "CircuitExtractionTask",
    "CircuitFromID",
    "CircuitSimulationScanConfig",
    "CircuitSimulationSingleConfig",
    "CircuitStimulusUnion",
    "ClusteredGroupedMorphologyLocations",
    "ClusteredMorphologyLocations",
    "ClusteredPDSynapsesByCount",
    "ClusteredPDSynapsesByMaxDistance",
    "ClusteredPathDistanceMorphologyLocations",
    "ClusteredSynapsesByCount",
    "ClusteredSynapsesByMaxDistance",
    "CombinedNeuronSet",
    "ConnectSynapticManipulation",
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
    "CreateExtracellularRecordingArrayScanConfig",
    "CreateExtracellularRecordingArraySingleConfig",
    "CreateExtracellularRecordingArrayTask",
    "DelayedInterNeuronSetSynapticManipulation",
    "DisconnectSynapticManipulation",
    "EMCellMeshFromID",
    "EMSynapseMappingInputNamedTuple",
    "EMSynapseMappingScanConfig",
    "EMSynapseMappingSingleConfig",
    "EMSynapseMappingTask",
    "ElectrophysiologyMetricsScanConfig",
    "ElectrophysiologyMetricsSingleConfig",
    "ElectrophysiologyMetricsTask",
    "EntityFromID",
    "ExcitatoryNeurons",
    "ExcitatoryTsodyksMarkramSynapticModel",
    "ExponentialDistribution",
    "ExtracellularLocations",
    "ExtracellularLocationsReference",
    "ExtracellularLocationsUnion",
    "FloatConstantDistribution",
    "FloatRange",
    "FloatUniformDistribution",
    "FolderCompressionScanConfig",
    "FolderCompressionSingleConfig",
    "FolderCompressionTask",
    "FullySynchronousSpikeStimulus",
    "GammaDistribution",
    "GenerateSimulationTask",
    "GlobalVariableInterNeuronSetSynapticManipulation",
    "GridExtracellularLocations",
    "GridScan",
    "GridScanGenerationTask",
    "HyperpolarizingCurrentClampSomaticStimulus",
    "IDNeuronSet",
    "Info",
    "InhibitoryNeurons",
    "InhibitoryTsodyksMarkramSynapticModel",
    "IntConstantDistribution",
    "IntDiscreteDistribution",
    "IntRange",
    "IntUniformDistribution",
    "InterNeuronSetSynapticManipulation",
    "InterNeuronSetSynapticModelAssigner",
    "InterSpikeIntervalDistributionSpikeStimulus",
    "IonChannelFittingScanConfig",
    "IonChannelFittingSingleConfig",
    "IonChannelFittingTask",
    "IonChannelModelSimulationScanConfig",
    "IonChannelModelSimulationSingleConfig",
    "LearningEngineCircuitSimulationScanConfig",
    "LearningEngineCircuitSimulationSingleConfig",
    "LinearCurrentClampSomaticStimulus",
    "LinearExtracellularLocations",
    "LoadAssetMethod",
    "LogNormalDistribution",
    "MEModelCircuit",
    "MEModelFromID",
    "MEModelSimulationScanConfig",
    "MEModelSimulationSingleConfig",
    "MEModelStimulusUnion",
    "MEModelWithSynapsesCircuitFromID",
    "MEModelWithSynapsesCircuitSimulationScanConfig",
    "MEModelWithSynapsesCircuitSimulationSingleConfig",
    "ModSpecificVariableInterNeuronSetSynapticManipulation",
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
    "MultiPopulationPredefinedNeuronSet",
    "MultiPulseCurrentClampSomaticStimulus",
    "NamedPath",
    "NamedTuple",
    "NeuronPropertyFilter",
    "NeuronSet",
    "Neuropixels1ExtracellularLocations",
    "NonNegativeFloatRange",
    "NonNegativeIntRange",
    "NonVirtualCombinedNeuronSet",
    "NormalDistribution",
    "NormallyDistributedCurrentClampSomaticStimulus",
    "OBIBaseModel",
    "OBIONEError",
    "OrnsteinUhlenbeckConductanceSomaticStimulus",
    "OrnsteinUhlenbeckCurrentSomaticStimulus",
    "PathDistanceConstrainedFractionOfSynapses",
    "PathDistanceConstrainedNumberOfSynapses",
    "PathDistanceMorphologyLocations",
    "PathDistanceWeightedFractionOfSynapses",
    "PathDistanceWeightedNumberOfSynapses",
    "PointCombinedNeuronSet",
    "PointNeuronSetReference",
    "PointPopulationIDNeuronSet",
    "PointPopulationNeuronSet",
    "PointPopulationPredefinedNeuronSet",
    "PointPopulationPropertyNeuronSet",
    "PoissonDistribution",
    "PoissonSpikeStimulus",
    "PositiveFloatRange",
    "PositiveIntRange",
    "PredefinedNeuronSet",
    "PresynapticNeuronSetSynapticModelAssigner",
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
    "RelativeOrnsteinUhlenbeckConductanceSomaticStimulus",
    "RelativeOrnsteinUhlenbeckCurrentSomaticStimulus",
    "ScaleAcetylcholineUSESynapticManipulation",
    "ScanConfig",
    "ScanConfigsUnion",
    "ScanGenerationTask",
    "Simulation",
    "SimulationsForm",
    "SingleConfigMixin",
    "SingleTimestamp",
    "SinusoidalCurrentClampSomaticStimulus",
    "SinusoidalPoissonSpikeStimulus",
    "SkeletonizationScanConfig",
    "SkeletonizationSingleConfig",
    "SomaVoltageRecording",
    "SpatiallyUniformElectricFieldStimulus",
    "SpikeTimeDistributionSpikeStimulus",
    "StimulusReference",
    "StimulusUnion",
    "SubthresholdCurrentClampSomaticStimulus",
    "SynapseParameterizationScanConfig",
    "SynapseParameterizationSingleConfig",
    "SynapseParameterizationTask",
    "SynapseSetUnion",
    "SynapticMgManipulation",
    "SynapticModelAssignerReference",
    "SynapticModelAssignerUnion",
    "SynapticModelReference",
    "SynapticModelUnion",
    "Task",
    "TasksUnion",
    "TemporallyCosineSpatiallyUniformElectricFieldStimulus",
    "TimeWindowSomaVoltageRecording",
    "TimestampsReference",
    "TimestampsUnion",
    "UTAHArrayExtracellularLocations",
    "VirtualCombinedNeuronSet",
    "VirtualNeuronSetReference",
    "VirtualPopulationIDNeuronSet",
    "VirtualPopulationNeuronSet",
    "VirtualPopulationPredefinedNeuronSet",
    "VirtualPopulationPropertyNeuronSet",
    "WeightChangeDelayedInterNeuronSetSynapticManipulation",
    "XYZExtracellularLocations",
    "add_node_set_to_circuit",
    "deserialize_obi_object_from_json_data",
    "deserialize_obi_object_from_json_file",
    "get_configs_task_type",
    "nbS1POmInputs",
    "nbS1VPMInputs",
    "rCA1CA3Inputs",
    "run_task_for_single_config",
    "run_task_for_single_config_asset",
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
from obi_one.scientific.blocks.afferent_synapses.afferent_synapses import (
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
from obi_one.scientific.blocks.distributions.constant import (
    FloatConstantDistribution,
    IntConstantDistribution,
)
from obi_one.scientific.blocks.distributions.discrete import IntDiscreteDistribution
from obi_one.scientific.blocks.distributions.exponential import ExponentialDistribution
from obi_one.scientific.blocks.distributions.gamma import GammaDistribution
from obi_one.scientific.blocks.distributions.lognormal import LogNormalDistribution
from obi_one.scientific.blocks.distributions.normal import NormalDistribution
from obi_one.scientific.blocks.distributions.poisson import PoissonDistribution
from obi_one.scientific.blocks.distributions.uniform import (
    FloatUniformDistribution,
    IntUniformDistribution,
)
from obi_one.scientific.blocks.extracellular_locations.extracellular_locations import (
    ExtracellularLocations,
    GridExtracellularLocations,
    LinearExtracellularLocations,
    Neuropixels1ExtracellularLocations,
    UTAHArrayExtracellularLocations,
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
from obi_one.scientific.blocks.neuron_sets.combined import (
    BiophysicalCombinedNeuronSet,
    CombinedNeuronSet,
    NonVirtualCombinedNeuronSet,
    PointCombinedNeuronSet,
    VirtualCombinedNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets.deprecated import (
    ExcitatoryNeurons,
    IDNeuronSet,
    InhibitoryNeurons,
    PredefinedNeuronSet,
    nbS1POmInputs,
    nbS1VPMInputs,
    rCA1CA3Inputs,
)
from obi_one.scientific.blocks.neuron_sets.id import (
    BiophysicalPopulationIDNeuronSet,
    PointPopulationIDNeuronSet,
    VirtualPopulationIDNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets.population import (
    BiophysicalPopulationNeuronSet,
    PointPopulationNeuronSet,
    VirtualPopulationNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets.predefined import (
    BiophysicalPopulationPredefinedNeuronSet,
    MultiPopulationPredefinedNeuronSet,
    PointPopulationPredefinedNeuronSet,
    VirtualPopulationPredefinedNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets.property import (
    BiophysicalPopulationPropertyNeuronSet,
    NeuronPropertyFilter,
    PointPopulationPropertyNeuronSet,
    VirtualPopulationPropertyNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets.specific import (
    AllBiophysicalNeurons,
    AllNonVirtualNeurons,
    AllPointNeurons,
    AllPopulationNeurons,
    AllVirtualNeurons,
)
from obi_one.scientific.blocks.recordings.base import Recording
from obi_one.scientific.blocks.recordings.soma import (
    SomaVoltageRecording,
    TimeWindowSomaVoltageRecording,
)
from obi_one.scientific.blocks.stimuli.electric_field import (
    SpatiallyUniformElectricFieldStimulus,
    TemporallyCosineSpatiallyUniformElectricFieldStimulus,
)
from obi_one.scientific.blocks.stimuli.ornstein_uhlenbeck import (
    OrnsteinUhlenbeckConductanceSomaticStimulus,
    OrnsteinUhlenbeckCurrentSomaticStimulus,
    RelativeOrnsteinUhlenbeckConductanceSomaticStimulus,
    RelativeOrnsteinUhlenbeckCurrentSomaticStimulus,
)
from obi_one.scientific.blocks.stimuli.spike import (
    FullySynchronousSpikeStimulus,
    PoissonSpikeStimulus,
    SinusoidalPoissonSpikeStimulus,
)
from obi_one.scientific.blocks.stimuli.spike.isi_distribution import (
    InterSpikeIntervalDistributionSpikeStimulus,
)
from obi_one.scientific.blocks.stimuli.spike.time_distribution import (
    SpikeTimeDistributionSpikeStimulus,
)
from obi_one.scientific.blocks.stimuli.stimulus import (
    ConstantCurrentClampSomaticStimulus,
    HyperpolarizingCurrentClampSomaticStimulus,
    LinearCurrentClampSomaticStimulus,
    MultiPulseCurrentClampSomaticStimulus,
    NormallyDistributedCurrentClampSomaticStimulus,
    RelativeConstantCurrentClampSomaticStimulus,
    RelativeLinearCurrentClampSomaticStimulus,
    RelativeNormallyDistributedCurrentClampSomaticStimulus,
    SinusoidalCurrentClampSomaticStimulus,
    SubthresholdCurrentClampSomaticStimulus,
)
from obi_one.scientific.blocks.synaptic_manipulations.base import (
    DelayedInterNeuronSetSynapticManipulation,
    GlobalVariableInterNeuronSetSynapticManipulation,
    InterNeuronSetSynapticManipulation,
    ModSpecificVariableInterNeuronSetSynapticManipulation,
    WeightChangeDelayedInterNeuronSetSynapticManipulation,
)
from obi_one.scientific.blocks.synaptic_manipulations.connect_disconnect import (
    ConnectSynapticManipulation,
    DisconnectSynapticManipulation,
)
from obi_one.scientific.blocks.synaptic_manipulations.demo import (
    ScaleAcetylcholineUSESynapticManipulation,
    SynapticMgManipulation,
)
from obi_one.scientific.blocks.synaptic_model_assigners.all_pairs import (
    AllPairsSynapticModelAssigner,
)
from obi_one.scientific.blocks.synaptic_model_assigners.inter_neuron_set import (
    InterNeuronSetSynapticModelAssigner,
)
from obi_one.scientific.blocks.synaptic_model_assigners.presyn_neuron_set import (
    PresynapticNeuronSetSynapticModelAssigner,
)
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram import (
    # CorrelatedExcitatoryTsodyksMarkramSynapticModel,
    ExcitatoryTsodyksMarkramSynapticModel,
    InhibitoryTsodyksMarkramSynapticModel,
)
from obi_one.scientific.blocks.timestamps.regular import RegularTimestamps
from obi_one.scientific.blocks.timestamps.single import SingleTimestamp
from obi_one.scientific.from_id.cell_morphology_from_id import (
    CellMorphologyFromID,
)
from obi_one.scientific.from_id.circuit_from_id import (
    CircuitFromID,
    MEModelWithSynapsesCircuitFromID,
)
from obi_one.scientific.from_id.em_cell_mesh_from_id import EMCellMeshFromID
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
from obi_one.scientific.tasks.create_recording_array.create_recording_array import (
    CreateExtracellularRecordingArrayScanConfig,
    CreateExtracellularRecordingArraySingleConfig,
    CreateExtracellularRecordingArrayTask,
)
from obi_one.scientific.tasks.em_synapse_mapping.config import (
    EMSynapseMappingInputNamedTuple,
    EMSynapseMappingScanConfig,
    EMSynapseMappingSingleConfig,
)
from obi_one.scientific.tasks.em_synapse_mapping.task import (
    EMSynapseMappingTask,
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
from obi_one.scientific.tasks.generate_simulations.config.brian2.brian2_circuit import (
    Brian2CircuitSimulationScanConfig,
    Brian2CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.learning_engine.le_circuit import (
    LearningEngineCircuitSimulationScanConfig,
    LearningEngineCircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationScanConfig,
    CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_ion_channel_models import (
    IonChannelModelSimulationScanConfig,
    IonChannelModelSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model import (
    MEModelSimulationScanConfig,
    MEModelSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model_with_synapses import (  # noqa: E501
    MEModelWithSynapsesCircuitSimulationScanConfig,
    MEModelWithSynapsesCircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.task.task import (
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
from obi_one.scientific.tasks.skeletonization import (
    SkeletonizationScanConfig,
    SkeletonizationSingleConfig,
)
from obi_one.scientific.tasks.synapse_parameterization.config import (
    SynapseParameterizationScanConfig,
    SynapseParameterizationSingleConfig,
)
from obi_one.scientific.tasks.synapse_parameterization.task import SynapseParameterizationTask
from obi_one.scientific.unions.aliases import Simulation, SimulationsForm
from obi_one.scientific.unions.block_references import AllBlockReferenceTypes  # noqa: F401
from obi_one.scientific.unions.config_task_map import (
    get_configs_task_type,
)
from obi_one.scientific.unions.unions_distributions import (
    AllDistributionsReference,
    AllDistributionsUnion,
)
from obi_one.scientific.unions.unions_extracellular_locations import (
    ExtracellularLocationsReference,
    ExtracellularLocationsUnion,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    BiophysicalNeuronSetReference,
    PointNeuronSetReference,
    VirtualNeuronSetReference,
)
from obi_one.scientific.unions.unions_recordings import RecordingReference, RecordingUnion
from obi_one.scientific.unions.unions_scan_configs import ScanConfigsUnion
from obi_one.scientific.unions.unions_stimuli import (
    CircuitStimulusUnion,
    MEModelStimulusUnion,
    StimulusReference,
    StimulusUnion,
)
from obi_one.scientific.unions.unions_synapse_set import SynapseSetUnion
from obi_one.scientific.unions.unions_synaptic_model_assigner import (
    SynapticModelAssignerReference,
    SynapticModelAssignerUnion,
)
from obi_one.scientific.unions.unions_synaptic_models import (
    SynapticModelReference,
    SynapticModelUnion,
)
from obi_one.scientific.unions.unions_tasks import TasksUnion
from obi_one.scientific.unions.unions_timestamps import TimestampsReference, TimestampsUnion

LAB_ID_STAGING_TEST = "e6030ed8-a589-4be2-80a6-f975406eb1f6"  # noqa: RUF067
PROJECT_ID_STAGING_TEST = "2720f785-a3a2-4472-969d-19a53891c817"  # noqa: RUF067


class GridScan(GridScanGenerationTask):  # noqa: RUF067
    pass


class CoupledScan(CoupledScanGenerationTask):  # noqa: RUF067
    pass
