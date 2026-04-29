from typing import Annotated

from pydantic import Discriminator

from obi_one.scientific.tasks.basic_connectivity_plots import BasicConnectivityPlotsScanConfig
from obi_one.scientific.tasks.circuit_extraction import CircuitExtractionScanConfig
from obi_one.scientific.tasks.connectivity_matrix_extraction import (
    ConnectivityMatrixExtractionScanConfig,
)
from obi_one.scientific.tasks.contribute import ContributeMorphologyScanConfig
from obi_one.scientific.tasks.em_synapse_mapping.config import EMSynapseMappingScanConfig
from obi_one.scientific.tasks.ephys_extraction import ElectrophysiologyMetricsScanConfig
from obi_one.scientific.tasks.folder_compression import FolderCompressionScanConfig
from obi_one.scientific.tasks.generate_simulations.config.circuit import CircuitSimulationScanConfig
from obi_one.scientific.tasks.generate_simulations.config.ion_channel_models import (
    IonChannelModelSimulationScanConfig,
)
from obi_one.scientific.tasks.spike_sorting.dispatch.config import AINDEPhysDispatchScanConfig
from obi_one.scientific.tasks.generate_simulations.config.me_model import (
    MEModelSimulationScanConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.me_model_with_synapses import (
    MEModelWithSynapsesCircuitSimulationScanConfig,
)
from obi_one.scientific.tasks.ion_channel_modeling import IonChannelFittingScanConfig
from obi_one.scientific.tasks.morphology_containerization import (
    MorphologyContainerizationScanConfig,
)
from obi_one.scientific.tasks.morphology_decontainerization import (
    MorphologyDecontainerizationScanConfig,
)
from obi_one.scientific.tasks.morphology_locations import MorphologyLocationsScanConfig
from obi_one.scientific.tasks.morphology_metrics import MorphologyMetricsScanConfig
from obi_one.scientific.tasks.skeletonization import SkeletonizationScanConfig
from obi_one.scientific.unions.aliases import SimulationsForm

ScanConfigsUnion = Annotated[
    CircuitSimulationScanConfig
    | SimulationsForm  # Alias for backward compatibility
    | CircuitExtractionScanConfig
    | EMSynapseMappingScanConfig
    | BasicConnectivityPlotsScanConfig
    | ConnectivityMatrixExtractionScanConfig
    | ContributeMorphologyScanConfig
    | FolderCompressionScanConfig
    | MEModelSimulationScanConfig
    | MorphologyContainerizationScanConfig
    | ElectrophysiologyMetricsScanConfig
    | MorphologyDecontainerizationScanConfig
    | MorphologyMetricsScanConfig
    | MorphologyLocationsScanConfig
    | IonChannelFittingScanConfig
    | SkeletonizationScanConfig
    | MEModelWithSynapsesCircuitSimulationScanConfig
    | AINDEPhysDispatchScanConfig
    | IonChannelModelSimulationScanConfig,
    Discriminator("type"),
]
