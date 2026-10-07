"""Compatibility re-export; implementation lives in obi_one_lazy."""

# ruff: file-ignore[undefined-local-with-import-star, import-private-name, unused-import, unsorted-imports]

from obi_one_lazy.scientific.library.build_synaptome import *

from obi_one_lazy.scientific.library.build_synaptome import (
    _PRE_IDX,
    _SEC_ID,
    _SEC_LOC,
    _SEC_TYP,
    _SEG_ID,
    _SEG_OFF,
    _SOURCE_ID,
    _STAGED_MECHANISMS_DIR_NAME,
    _TARGET_ID,
    _append_population_config,
    _derive_group_seed,
    _fold_staged_mechanisms_into,
    _generate_locations,
    _location_edge_properties,
    _preserve_numpy_random_state,
    _safe_name,
    _sample_physiology,
    _target_population,
)
