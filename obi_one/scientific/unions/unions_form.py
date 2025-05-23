from obi_one.scientific.basic_connectivity_plots.basic_connectivity_plots import (
    BasicConnectivityPlots,
)
from obi_one.scientific.circuit_extraction.circuit_extraction import (
    CircuitExtractions,
)
from obi_one.scientific.connectivity_matrix_extraction.connectivity_matrix_extraction import (
    ConnectivityMatrixExtractions,
)
from obi_one.scientific.folder_compression.folder_compression import (
    FolderCompressions,
)
from obi_one.scientific.morphology_containerization.morphology_containerization import (
    MorphologyContainerizationsForm,
)
from obi_one.scientific.morphology_containerization.morphology_decontainerization import (
    MorphologyDecontainerizationsForm,
)
from obi_one.scientific.morphology_locations import MorphologyLocationsForm
from obi_one.scientific.morphology_metrics.morphology_metrics import (
    MorphologyMetricsForm,
)
from obi_one.scientific.simulation.simulations import SimulationsForm
from obi_one.scientific.test_forms.test_form_single_block import (
    MultiBlockEntitySDKTestForm,
    SingleBlockEntityTestForm,
    SingleBlockGenerateTestForm,
)

FormUnion = (
    BasicConnectivityPlots
    | CircuitExtractions
    | ConnectivityMatrixExtractions
    | FolderCompressions
    | MorphologyContainerizationsForm
    | MorphologyDecontainerizationsForm
    | MorphologyMetricsForm
    | SimulationsForm
    | SingleBlockGenerateTestForm
    | SingleBlockEntityTestForm
    | MultiBlockEntitySDKTestForm
    | MorphologyLocationsForm
)
