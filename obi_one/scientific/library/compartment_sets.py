"""Compatibility re-export; implementation lives in obi_one_lazy."""

# ruff: file-ignore[undefined-local-with-import-star, import-private-name, unused-import, unsorted-imports]

from obi_one_lazy.scientific.library.compartment_sets import *

from obi_one_lazy.scientific.library.compartment_sets import (
    _iter_morphologies,
    _raise_empty_compartment_set,
    _validate_compartment_set_entry_count,
)
