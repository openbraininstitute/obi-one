from typing import Annotated

from pydantic import Discriminator

from obi_one.scientific.morphology_metrics.morphology_metrics import (
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
    | FolderCompressions
    | MorphologyContainerizationsForm
    | MorphologyDecontainerizationsForm
    | MorphologyMetricsForm
    | SimulationsForm
    | MorphologyLocationsForm,
    Discriminator("type"),
]
