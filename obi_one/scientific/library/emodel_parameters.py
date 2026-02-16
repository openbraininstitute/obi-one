"""Fetch and parse emodel parameters for mechanism variable modifications."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import entitysdk.client
from entitysdk.models import EModel, MEModel
from entitysdk.types import AssetLabel
from pydantic import BaseModel

if TYPE_CHECKING:
    import entitysdk.exception

_VARIABLE_SECTION_PARTS = 2

L = logging.getLogger(__name__)


class MechanismVariable(BaseModel):
    neuron_variable: str
    section_list: str
    value: float | None = None
    units: str = ""
    limits: list[float] | None = None


def get_mechanism_variables(
    db_client: entitysdk.client.Client,
    memodel: MEModel,
) -> list[MechanismVariable]:
    """Fetch all modifiable mechanism variables for an MEModel.

    Retrieves optimized parameters from the emodel_optimization_output asset and
    additional RANGE/GLOBAL variables from ion channel models.
    """
    emodel = db_client.get_entity(entity_id=memodel.emodel.id, entity_type=EModel)

    optimized_params = _fetch_optimization_parameters(db_client, emodel)
    ion_channel_vars = _get_ion_channel_variables(emodel)

    # Merge: keep optimized params; add ion channel vars not already present
    optimized_var_names = {p.neuron_variable for p in optimized_params}
    merged = list(optimized_params)
    merged.extend(var for var in ion_channel_vars if var.neuron_variable not in optimized_var_names)

    # Special TTX entry
    merged.append(MechanismVariable(neuron_variable="TTX", section_list=""))

    return merged


def _fetch_optimization_parameters(
    db_client: entitysdk.client.Client,
    emodel: EModel,
) -> list[MechanismVariable]:
    """Download and parse the emodel_optimization_output asset."""
    asset = _find_optimization_output_asset(emodel)
    if asset is None:
        L.warning("No emodel_optimization_output asset found for EModel %s", emodel.id)
        return []

    content_bytes = db_client.download_content(
        entity_id=emodel.id,
        entity_type=EModel,
        asset_id=asset.id,
    )
    data = json.loads(content_bytes)
    return _parse_optimization_parameters(data.get("parameter", []))


def _find_optimization_output_asset(emodel: EModel) -> object | None:
    """Find the emodel_optimization_output asset on an EModel entity."""
    if not emodel.assets:
        return None
    for asset in emodel.assets:
        if asset.label == AssetLabel.emodel_optimization_output:
            return asset
    return None


def _parse_optimization_parameters(parameters_json: list[dict]) -> list[MechanismVariable]:
    """Parse the 'parameter' array from the emodel optimization output JSON.

    Each parameter name follows the format "<neuron_variable>.<section_list>"
    (e.g. "decay_CaDynamics_DC0.somatic", "g_pas.all").
    """
    parsed = []
    for param in parameters_json:
        name = param.get("name", "")
        value = param.get("value")
        parts = name.split(".", 1)
        if len(parts) == _VARIABLE_SECTION_PARTS:
            neuron_variable, section_list = parts
        else:
            neuron_variable = parts[0]
            section_list = "all"

        # Add limits for variables starting with 'g'
        limits = [0.0, 10.0] if neuron_variable.startswith("g") else None

        parsed.append(
            MechanismVariable(
                neuron_variable=neuron_variable,
                section_list=section_list,
                value=value,
                limits=limits,
            )
        )
    return parsed


def _create_mechanism_variable_from_ion_channel(
    var_name: str,
    var_units: str,
    suffix: str,
) -> MechanismVariable | None:
    """Create a MechanismVariable from ion channel metadata.

    Filters out variables starting with 'i' (ionic currents).
    Adds limits [0,10] for variables starting with 'g'.
    """
    # Filter out variables starting with 'i' (ionic currents)
    if var_name.startswith("i"):
        return None

    neuron_variable = f"{var_name}_{suffix}"
    limits = [0.0, 10.0] if neuron_variable.startswith("g") else None

    return MechanismVariable(
        neuron_variable=neuron_variable,
        section_list="all",
        units=var_units if isinstance(var_units, str) else "",
        limits=limits,
    )


def _process_neuron_block_entries(
    entries: list[dict],
    suffix: str,
) -> list[MechanismVariable]:
    """Process RANGE or GLOBAL entries from a neuron block."""
    variables = []
    for entry in entries:
        for var_name, var_units in entry.items():
            var = _create_mechanism_variable_from_ion_channel(var_name, var_units, suffix)
            if var is not None:
                variables.append(var)
    return variables


def _get_ion_channel_variables(emodel: EModel) -> list[MechanismVariable]:
    """Extract RANGE and GLOBAL variables from ion channel models on the EModel.

    Constructs NEURON variable names in the format {variable}_{nmodl_suffix}.
    Returns with section_list="all" and value=None (user checks defaults on platform).
    Filters out variables starting with 'i' (ionic currents that cannot be modified).
    """
    variables = []
    if not emodel.ion_channel_models:
        return variables

    for icm in emodel.ion_channel_models:
        suffix = icm.nmodl_suffix
        neuron_block = icm.neuron_block
        if neuron_block is None:
            continue

        if neuron_block.range:
            variables.extend(_process_neuron_block_entries(neuron_block.range, suffix))

        if neuron_block.global_:
            variables.extend(_process_neuron_block_entries(neuron_block.global_, suffix))

    return variables
