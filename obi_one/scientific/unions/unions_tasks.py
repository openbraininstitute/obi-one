from typing import Annotated

from pydantic import Discriminator

from obi_one.scientific.tasks.basic_connectivity_plots import BasicConnectivityPlotsTask
from obi_one.scientific.tasks.circuit_extraction import CircuitExtractionTask
from obi_one.scientific.tasks.connectivity_matrix_extraction import ConnectivityMatrixExtractionTask
from obi_one.scientific.tasks.contribute import ContributeMorphologyTask
from obi_one.scientific.tasks.ephys_extraction import ElectrophysiologyMetricsTask
from obi_one.scientific.tasks.folder_compression import FolderCompressionTask
from obi_one.scientific.tasks.generate_simulation_task import GenerateSimulationTask
from obi_one.scientific.tasks.ion_channel_modeling import IonChannelFittingTask
from obi_one.scientific.tasks.morphology_containerization import MorphologyContainerizationTask
from obi_one.scientific.tasks.morphology_decontainerization import MorphologyDecontainerizationTask
from obi_one.scientific.tasks.morphology_locations import MorphologyLocationsTask
from obi_one.scientific.tasks.morphology_metrics import MorphologyMetricsTask

TasksUnion = Annotated[
    GenerateSimulationTask
    | CircuitExtractionTask
    | ContributeMorphologyTask
    | BasicConnectivityPlotsTask
    | ConnectivityMatrixExtractionTask
    | ElectrophysiologyMetricsTask
    | FolderCompressionTask
    | IonChannelFittingTask
    | MorphologyContainerizationTask
    | MorphologyDecontainerizationTask
    | MorphologyMetricsTask
    | MorphologyLocationsTask,
    Discriminator("type"),
]
