"""Compatibility re-export; implementation lives in obi_one_lazy."""

# ruff: file-ignore[undefined-local-with-import-star, import-private-name, unused-import, unsorted-imports, suppressible-exception]

from obi_one_lazy.scientific.library.find_afferent_synapses import *

from obi_one_lazy.scientific.library.find_afferent_synapses import (
    _pd_gaussian_selector,
)

try:
    from obi_one_lazy.scientific.library.find_afferent_synapses import (
        MorphologyPathDistanceCalculator,
    )
except ImportError:
    pass
