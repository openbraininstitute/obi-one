"""Compatibility re-export; implementation lives in obi_one_lazy."""

# ruff: file-ignore[undefined-local-with-import-star, suppressible-exception, unused-import]

from obi_one_lazy.scientific.library.simplex_extractors import *

try:
    from obi_one_lazy.scientific.library.simplex_extractors import list_simplices_by_dimension
except ImportError:
    pass
