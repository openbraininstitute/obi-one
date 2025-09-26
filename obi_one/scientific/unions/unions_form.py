from typing import Annotated

from pydantic import Discriminator

from obi_one.scientific.tasks.morphology_metrics_task import (
    MorphologyMetricsForm,
)
from obi_one.scientific.tasks.basic_connectivity_plots import (
    BasicConnectivityPlots,
)
from obi_one.scientific.tasks.circuit_extraction import (
    CircuitExtractions,
)
from obi_one.scientific.tasks.connectivity_matrix_extraction import (
    ConnectivityMatrixExtractions,
)
from obi_one.scientific.tasks.ephys_extraction_task import ElectrophysiologyMetricsForm
from obi_one.scientific.tasks.folder_compression import (
    FolderCompressions,
)
from obi_one.scientific.tasks.morphology_containerization import (
    MorphologyContainerizationsForm,
)
from obi_one.scientific.tasks.morphology_decontainerization import (
    MorphologyDecontainerizationsForm,
)
from obi_one.scientific.tasks.morphology_location_form import MorphologyLocationsForm
from obi_one.scientific.tasks.simulations import SimulationsForm

FormUnion = Annotated[
    BasicConnectivityPlots
    | CircuitExtractions
    | ConnectivityMatrixExtractions
    | ElectrophysiologyMetricsForm
    | FolderCompressions
    | MorphologyContainerizationsForm
    | MorphologyDecontainerizationsForm
    | MorphologyMetricsForm
    | SimulationsForm
    | MorphologyLocationsForm,
    Discriminator("type"),
]
