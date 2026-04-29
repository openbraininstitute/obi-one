from typing import Annotated

from pydantic import Discriminator

from obi_one.scientific.tasks.basic_connectivity_plots import BasicConnectivityPlotsTask
from obi_one.scientific.tasks.circuit_extraction import CircuitExtractionTask
from obi_one.scientific.tasks.connectivity_matrix_extraction import ConnectivityMatrixExtractionTask
from obi_one.scientific.tasks.contribute import ContributeMorphologyTask
from obi_one.scientific.tasks.ephys_extraction import ElectrophysiologyMetricsTask
from obi_one.scientific.tasks.folder_compression import FolderCompressionTask
from obi_one.scientific.tasks.generate_simulations.task.task import GenerateSimulationTask
from obi_one.scientific.tasks.ion_channel_modeling import IonChannelFittingTask
from obi_one.scientific.tasks.morphology_containerization import MorphologyContainerizationTask
from obi_one.scientific.tasks.morphology_decontainerization import MorphologyDecontainerizationTask
from obi_one.scientific.tasks.morphology_locations import MorphologyLocationsTask
from obi_one.scientific.tasks.morphology_metrics import MorphologyMetricsTask
from obi_one.scientific.tasks.skeletonization import SkeletonizationTask
from obi_one.scientific.tasks.aind_ephys._01_dispatch.task import AINDEPhysDispatchTask
from obi_one.scientific.tasks.aind_ephys._02_preprocessing.task import AINDEPhysPreprocessingTask
from obi_one.scientific.tasks.aind_ephys._05_curation.task import (
    AINDEPhysCurationTask,
)
from obi_one.scientific.tasks.aind_ephys._08_processing_qc.task import (
    AINDEPhysProcessingQCTask,
)
from obi_one.scientific.tasks.aind_ephys._10_ecephys_nwb.task import (
    AINDEcephysNWBTask,
)
from obi_one.scientific.tasks.aind_ephys._11_units_nwb.task import (
    AINDUnitsNWBTask,
)
from obi_one.scientific.tasks.aind_ephys._09_qc_collector.task import (
    AINDEPhysQCCollectorTask,
)
from obi_one.scientific.tasks.aind_ephys._07_results_collector.task import (
    AINDEPhysResultsCollectorTask,
)
from obi_one.scientific.tasks.aind_ephys._06_visualization.task import (
    AINDEPhysVisualizationTask,
)
from obi_one.scientific.tasks.aind_ephys._04_postprocessing.task import (
    AINDEPhysPostprocessingTask,
)
from obi_one.scientific.tasks.aind_ephys._03_kilosort4.task import (
    AINDEPhysSpikesortKilosort4Task,
)

TasksUnion = Annotated[
    GenerateSimulationTask
    | CircuitExtractionTask
    | ContributeMorphologyTask
    | BasicConnectivityPlotsTask
    | ConnectivityMatrixExtractionTask
    | ElectrophysiologyMetricsTask
    | FolderCompressionTask
    | IonChannelFittingTask
    | SkeletonizationTask
    | MorphologyContainerizationTask
    | MorphologyDecontainerizationTask
    | MorphologyMetricsTask
    | AINDEPhysDispatchTask
    | AINDEPhysPreprocessingTask
    | AINDEPhysSpikesortKilosort4Task
    | AINDEPhysPostprocessingTask
    | AINDEPhysCurationTask
    | AINDEPhysVisualizationTask
    | AINDEPhysResultsCollectorTask
    | AINDEPhysProcessingQCTask
    | AINDEPhysQCCollectorTask
    | AINDEcephysNWBTask
    | AINDUnitsNWBTask
    | MorphologyLocationsTask,
    Discriminator("type"),
]
