from obi_one.scientific.tasks.basic_connectivity_plots import (
    BasicConnectivityPlotsSingleConfig,
    BasicConnectivityPlotsTask,
)
from obi_one.scientific.tasks.circuit_extraction import (
    CircuitExtractionSingleConfig,
    CircuitExtractionTask,
)
from obi_one.scientific.tasks.connectivity_matrix_extraction import (
    ConnectivityMatrixExtractionSingleConfig,
    ConnectivityMatrixExtractionTask,
)
from obi_one.scientific.tasks.contribute import (
    ContributeMorphologySingleConfig,
    ContributeMorphologyTask,
)
from obi_one.scientific.tasks.ephys_extraction import (
    ElectrophysiologyMetricsSingleConfig,
    ElectrophysiologyMetricsTask,
)
from obi_one.scientific.tasks.folder_compression import (
    FolderCompressionSingleConfig,
    FolderCompressionTask,
)
from obi_one.scientific.tasks.generate_simulation_configs import (
    CircuitSimulationSingleConfig,
    MEModelSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulation_task import (
    GenerateSimulationTask,
)
from obi_one.scientific.tasks.ion_channel_modeling import (
    IonChannelFittingSingleConfig,
    IonChannelFittingTask,
)
from obi_one.scientific.tasks.morphology_containerization import (
    MorphologyContainerizationSingleConfig,
    MorphologyContainerizationTask,
)
from obi_one.scientific.tasks.morphology_decontainerization import (
    MorphologyDecontainerizationSingleConfig,
    MorphologyDecontainerizationTask,
)
from obi_one.scientific.tasks.morphology_locations import (
    MorphologyLocationsSingleConfig,
    MorphologyLocationsTask,
)
from obi_one.scientific.tasks.morphology_metrics import (
    MorphologyMetricsSingleConfig,
    MorphologyMetricsTask,
)
from obi_one.scientific.unions.aliases import Simulation

_config_tasks_map = {
    Simulation: GenerateSimulationTask,
    CircuitSimulationSingleConfig: GenerateSimulationTask,
    CircuitExtractionSingleConfig: CircuitExtractionTask,
    MEModelSimulationSingleConfig: GenerateSimulationTask,
    ContributeMorphologySingleConfig: ContributeMorphologyTask,
    BasicConnectivityPlotsSingleConfig: BasicConnectivityPlotsTask,
    ConnectivityMatrixExtractionSingleConfig: ConnectivityMatrixExtractionTask,
    ElectrophysiologyMetricsSingleConfig: ElectrophysiologyMetricsTask,
    FolderCompressionSingleConfig: FolderCompressionTask,
    IonChannelFittingSingleConfig: IonChannelFittingTask,
    MorphologyContainerizationSingleConfig: MorphologyContainerizationTask,
    MorphologyDecontainerizationSingleConfig: MorphologyDecontainerizationTask,
    MorphologyMetricsSingleConfig: MorphologyMetricsTask,
    MorphologyLocationsSingleConfig: MorphologyLocationsTask,
}


def get_configs_task_type(config: object) -> type:
    return _config_tasks_map[config.__class__]
