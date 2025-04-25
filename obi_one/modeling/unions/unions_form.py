from obi_one.modeling.unions.unions import subclass_union
from obi_one.core.form import Form
from obi_one.modeling.simulation.simulations import *
from obi_one.modeling.circuit_extraction.circuit_extraction import *
from obi_one.modeling.connectivity_matrix_extraction.connectivity_matrix_extraction import *
from obi_one.modeling.basic_connectivity_plots.basic_connectivity_plots import *
from obi_one.modeling.folder_compression.folder_compression import *
from obi_one.modeling.morphology_containerization.morphology_containerization import *
from obi_one.modeling.morphology_metrics.morphology_metrics import *
from obi_one.modeling.morphology_metrics.morphology_metrics_example import *
from obi_one.modeling.test_forms.test_form_single_block import *


FormUnion = subclass_union(Form)