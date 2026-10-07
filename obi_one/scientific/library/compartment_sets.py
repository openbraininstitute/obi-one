"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports, import-private-name]

from obi_one_lazy.scientific.library.compartment_sets import (
    annotations,
    Any,
    BaseModel,
    build_compartment_set_for_neuron_set,
    build_compartment_set_from_locations_block,
    CompartmentLocation,
    ConfigValidationError,
    Field,
    itemgetter,
    L,
    logging,
    MaterializedCompartmentSet,
    MAX_MATERIALIZED_COMPARTMENT_SET_ENTRIES,
    NoReturn,
    TYPE_CHECKING,
)

from obi_one_lazy.scientific.library.compartment_sets import (
    _iter_morphologies,
    _raise_empty_compartment_set,
    _validate_compartment_set_entry_count,
)

__all__ = [
    "annotations",
    "Any",
    "BaseModel",
    "build_compartment_set_for_neuron_set",
    "build_compartment_set_from_locations_block",
    "CompartmentLocation",
    "ConfigValidationError",
    "Field",
    "itemgetter",
    "L",
    "logging",
    "MaterializedCompartmentSet",
    "MAX_MATERIALIZED_COMPARTMENT_SET_ENTRIES",
    "NoReturn",
    "TYPE_CHECKING",
    "_iter_morphologies",
    "_raise_empty_compartment_set",
    "_validate_compartment_set_entry_count",
]
