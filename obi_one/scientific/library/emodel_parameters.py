"""Fetch and parse emodel parameters for mechanism variable modifications."""

from __future__ import annotations

import json
import logging

import entitysdk.client
import entitysdk.exception
from entitysdk.models import EModel, MEModel
from entitysdk.types import AssetLabel
from pydantic import BaseModel

L = logging.getLogger(__name__)


class MechanismVariable(BaseModel):
    neuron_variable: str
    section_list: str
    value: float | None = None


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
    for var in ion_channel_vars:
        if var.neuron_variable not in optimized_var_names:
            merged.append(var)

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


def _find_optimization_output_asset(emodel: EModel):
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
        if len(parts) == 2:
            neuron_variable, section_list = parts
        else:
            neuron_variable = parts[0]
            section_list = "all"
        parsed.append(
            MechanismVariable(
                neuron_variable=neuron_variable,
                section_list=section_list,
                value=value,
            )
        )
    return parsed


def _get_ion_channel_variables(emodel: EModel) -> list[MechanismVariable]:
    """Extract RANGE and GLOBAL variables from ion channel models on the EModel.

    Constructs NEURON variable names in the format {variable}_{nmodl_suffix}.
    Returns with section_list="all" and value=None (user checks defaults on platform).
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
            for range_entry in neuron_block.range:
                for var_name in range_entry:
                    variables.append(
                        MechanismVariable(
                            neuron_variable=f"{var_name}_{suffix}",
                            section_list="all",
                        )
                    )

        if neuron_block.global_:
            for global_entry in neuron_block.global_:
                for var_name in global_entry:
                    variables.append(
                        MechanismVariable(
                            neuron_variable=f"{var_name}_{suffix}",
                            section_list="all",
                        )
                    )

    return variables
