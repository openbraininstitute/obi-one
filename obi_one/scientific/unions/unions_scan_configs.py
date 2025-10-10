from typing import Annotated

from pydantic import Discriminator

from obi_one.scientific.tasks.basic_connectivity_plots import BasicConnectivityPlotsScanConfig
from obi_one.scientific.tasks.circuit_extraction import CircuitExtractionScanConfig
from obi_one.scientific.tasks.connectivity_matrix_extraction import (
    ConnectivityMatrixExtractionScanConfig,
)
from obi_one.scientific.tasks.contribute import ContributeMorphologyScanConfig
from obi_one.scientific.tasks.ephys_extraction import ElectrophysiologyMetricsScanConfig
from obi_one.scientific.tasks.folder_compression import FolderCompressionScanConfig
from obi_one.scientific.tasks.generate_simulation_configs import (
    CircuitSimulationScanConfig,
    MEModelSimulationScanConfig,
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
from obi_one.scientific.unions.aliases import SimulationsForm

ScanConfigsUnion = Annotated[
    CircuitSimulationScanConfig
    | SimulationsForm  # Alias for backward compatibility
    | CircuitExtractionScanConfig
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
    | IonChannelFittingScanConfig,
    Discriminator("type"),
]
