"""Compatibility re-export; implementation lives in obi_one_lazy."""

# ruff: file-ignore[undefined-local-with-import-star, import-private-name, unused-import, unsorted-imports, suppressible-exception]

from obi_one_lazy.scientific.library.morphology_mesh import *

from obi_one_lazy.scientific.library.morphology_mesh import (
    _mesh_swc,
    _validate_mesh_output,
)

try:
    from obi_one_lazy.scientific.library.morphology_mesh import HAS_MESHING
except ImportError:
    pass

try:
    from obi_one_lazy.scientific.library.morphology_mesh import NEURON_COLORS
except ImportError:
    pass

try:
    from obi_one_lazy.scientific.library.morphology_mesh import NeuronMorphology
except ImportError:
    pass
