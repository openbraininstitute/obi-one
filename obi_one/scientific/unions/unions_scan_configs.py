from typing import Annotated

from pydantic import Discriminator

from obi_one.scientific.tasks.basic_connectivity_plots import BasicConnectivityPlotsScanConfig
from obi_one.scientific.tasks.circuit_extraction import CircuitExtractionScanConfig
from obi_one.scientific.tasks.connectivity_matrix_extraction import (
    ConnectivityMatrixExtractionScanConfig,
)
from obi_one.scientific.tasks.contribute import ContributeMorphologyForm
from obi_one.scientific.tasks.ephys_extraction_task import ElectrophysiologyMetricsScanConfig
from obi_one.scientific.tasks.folder_compression import FolderCompressions
from obi_one.scientific.tasks.morphology_containerization import MorphologyContainerizationsForm
from obi_one.scientific.tasks.morphology_decontainerization import MorphologyDecontainerizationsForm
from obi_one.scientific.tasks.morphology_location_form import MorphologyLocationsForm
from obi_one.scientific.tasks.morphology_metrics_task import MorphologyMetricsTask
from obi_one.scientific.tasks.simulations import SimulationsForm

ScanConfigsUnion = Annotated[
    SimulationsForm
    | CircuitExtractionScanConfig
    | BasicConnectivityPlotsScanConfig
    | ConnectivityMatrixExtractionScanConfig
    | ContributeMorphologyForm
    | FolderCompressions
    | MorphologyContainerizationsForm
    | ElectrophysiologyMetricsScanConfig
    | MorphologyDecontainerizationsForm
    | MorphologyMetricsTask
    | MorphologyLocationsForm,
    Discriminator("type"),
]
