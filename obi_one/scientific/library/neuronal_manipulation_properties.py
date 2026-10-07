"""Compatibility re-export; implementation lives in obi_one_lazy."""

# ruff: file-ignore[undefined-local-with-import-star, import-private-name, unused-import, unsorted-imports]

from obi_one_lazy.scientific.library.neuronal_manipulation_properties import *

from obi_one_lazy.scientific.library.neuronal_manipulation_properties import (
    _build_emodel_groups,
    _build_mechanism_variables_by_ion_channel_response,
    _compute_common_mechanism_variables,
    _fetch_emodel_derivation_mapping,
    _get_circuit_asset,
    _match_templates_to_emodels,
    _stage_circuit_for_neuron_set,
    _stage_circuit_for_neuron_set_resolution,
    _stage_file,
)
