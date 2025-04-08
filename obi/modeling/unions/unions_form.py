from obi.modeling.unions.unions import subclass_union
from obi.modeling.core.form import Form
from obi.modeling.simulation.simulations import *
from obi.modeling.circuit_extraction.circuit_extraction import *
from obi.modeling.connectivity_matrix_extraction.connectivity_matrix_extraction import *
from obi.modeling.basic_connectivity_plots.basic_connectivity_plots import *
from obi.modeling.folder_compression.folder_compression import *
from obi.modeling.morphology_containerization.morphology_containerization import *


FormUnion = subclass_union(Form)