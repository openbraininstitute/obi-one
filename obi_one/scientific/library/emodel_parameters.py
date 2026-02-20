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
_MULTILOC_MAP = {
    "alldend": ["apical", "basal"],
    "somadend": ["apical", "basal", "somatic"],
    "allnoaxon": ["apical", "basal", "somatic"],
    "somaxon": ["axonal", "somatic"],
    "allact": ["apical", "basal", "somatic", "axonal"],
    "all": ["apical", "basal", "somatic", "axonal"],
}


def _expand_section_list(section_list: str) -> list[str]:
    """Expand a section-list alias into concrete section lists."""
    return _MULTILOC_MAP.get(section_list, [section_list])


def _expand_section_lists(section_lists: list[str]) -> list[str]:
    """Expand aliases in a list of section lists and keep order unique."""
    expanded: list[str] = []
    for section_list in section_lists:
        expanded.extend(_expand_section_list(section_list))
    return list(dict.fromkeys(expanded))


L = logging.getLogger(__name__)


class ChannelInfo(BaseModel):
    """Information about an ion channel."""

    section_lists: list[str]
    entity_id: str | None = None  # None for built-in mechanisms like pas


class ChannelSectionListMapping(BaseModel):
    """Mapping of ion channel names to their info (section lists and entity ID)."""

    channel_to_section_lists: dict[str, ChannelInfo]


class MechanismVariable(BaseModel):
    neuron_variable: str
    channel_name: str = ""
    section_list: str
    value: float | None = None
    units: str = ""
    limits: list[float] | None = None
    variable_type: str  # "RANGE" or "GLOBAL"


def _is_global_variable(emodel: EModel, neuron_variable: str) -> bool:
    """Check if a variable is GLOBAL by looking at emodel metadata neuron_block.global_.

    Args:
        emodel: The EModel entity containing ion channel models
        neuron_variable: Variable name to check (e.g., 'g_pas', 'e_pas')

    Returns:
        True if variable appears in neuron_block.global_, False otherwise
    """
    # Extract suffix to find the relevant ion channel model
    suffix = _extract_channel_suffix(
        neuron_variable, [icm.nmodl_suffix for icm in emodel.ion_channel_models or []]
    )

    if not suffix:
        return False

    # Find the ion channel model with this suffix
    for icm in emodel.ion_channel_models or []:
        if icm.nmodl_suffix == suffix:
            neuron_block = icm.neuron_block
            if neuron_block and neuron_block.global_:
                # Check if the variable name (without suffix) appears in global entries
                var_name = (
                    neuron_variable[: -(len(suffix) + 1)]
                    if neuron_variable.endswith(f"_{suffix}")
                    else neuron_variable
                )
                for global_entry in neuron_block.global_:
                    if var_name in global_entry:
                        return True
            break

    return False


def get_mechanism_variables(
    db_client: entitysdk.client.Client,
    memodel: MEModel,
) -> tuple[list[MechanismVariable], ChannelSectionListMapping]:
    """Fetch all modifiable mechanism variables for an MEModel.

    Retrieves optimized parameters from the emodel_optimization_output asset and
    additional RANGE/GLOBAL variables from ion channel models.

    Returns:
        Tuple of (variables_list, channel_mapping) where channel_mapping shows
        which section lists each ion channel appears in based on emodel JSON.
    """
    emodel = db_client.get_entity(entity_id=memodel.emodel.id, entity_type=EModel)

    optimized_params = _fetch_optimization_parameters(db_client, emodel)
    ion_channel_vars = _get_ion_channel_variables(emodel)

    # Build suffix-to-channel-name mapping from emodel's ion_channel_models
    suffix_to_channel_name = _build_suffix_to_channel_name_mapping(emodel)
    channel_entity_ids = _build_channel_entity_id_mapping(emodel)
    known_suffixes = list(suffix_to_channel_name.keys())

    # Build channel-to-section-lists mapping from emodel JSON variables
    channel_mapping = _build_channel_section_list_mapping(
        optimized_params, suffix_to_channel_name, channel_entity_ids, known_suffixes
    )

    # Deduplicate: prefer emodel JSON over ion channel metadata
    # For ion channel vars, build key as (neuron_variable, section_list)
    optimized_keys = {(p.neuron_variable, p.section_list) for p in optimized_params}

    # Apply section list inference to ion channel RANGE variables not in emodel JSON
    inferred_vars = _infer_section_lists_for_ion_channel_vars(
        ion_channel_vars, optimized_keys, channel_mapping, suffix_to_channel_name, known_suffixes
    )

    merged = list(optimized_params) + inferred_vars

    # Enrich all variables with channel_name derived from neuron_variable suffix
    merged = [
        var.model_copy(
            update={
                "channel_name": suffix_to_channel_name.get(
                    _extract_channel_suffix(var.neuron_variable, known_suffixes) or "",
                    _extract_channel_suffix(var.neuron_variable, known_suffixes) or "",
                )
            }
        )
        for var in merged
    ]

    return merged, channel_mapping


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
    return _parse_optimization_parameters(data.get("parameter", []), emodel)


def _find_optimization_output_asset(emodel: EModel) -> object | None:
    """Find the emodel_optimization_output asset on an EModel entity."""
    if not emodel.assets:
        return None
    for asset in emodel.assets:
        if asset.label == AssetLabel.emodel_optimization_output:
            return asset
    return None


def _parse_optimization_parameters(
    parameters_json: list[dict], emodel: EModel
) -> list[MechanismVariable]:
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

        # Determine variable type: GLOBAL only if in neuron_block.global_, otherwise RANGE
        variable_type = "GLOBAL" if _is_global_variable(emodel, neuron_variable) else "RANGE"

        expanded_section_lists = _expand_section_list(section_list)
        parsed.extend(
            MechanismVariable(
                neuron_variable=neuron_variable,
                section_list=expanded_section_list,
                value=value,
                limits=limits,
                variable_type=variable_type,
            )
            for expanded_section_list in expanded_section_lists
        )
    return parsed


def _extract_channel_suffix(neuron_variable: str, known_suffixes: list[str]) -> str | None:
    """Extract ion channel suffix from neuron variable name.

    Matches against known suffixes from metadata to handle suffixes with underscores.
    Falls back to simple extraction for built-in mechanisms.

    Examples:
    - 'gSK_E2bar_SK_E2' with known suffix 'SK_E2' -> 'SK_E2'
    - 'g_pas' (not in known_suffixes) -> 'pas'
    - 'gNap_Et2bar_Nap_Et2' with known suffix 'Nap_Et2' -> 'Nap_Et2'
    """
    if "_" not in neuron_variable:
        return None

    # First, check each known suffix to see if the variable ends with it
    # Sort by length descending to match longest suffix first
    for suffix in sorted(known_suffixes, key=len, reverse=True):
        if neuron_variable.endswith(f"_{suffix}"):
            return suffix

    # Fallback: extract the last part after underscore for built-in mechanisms
    # This handles cases like g_pas, e_pas, etc.
    return neuron_variable.rsplit("_", maxsplit=1)[-1]


def _build_suffix_to_channel_name_mapping(emodel: EModel) -> dict[str, str]:
    """Build mapping from nmodl_suffix to channel name.

    Example: {'NaTg': 'NaTg', 'Ca_HVA2': 'Ca_HVA2', 'CaDynamics_DC0': 'CaDynamics_DC0'}
    """
    mapping = {}
    if not emodel.ion_channel_models:
        return mapping

    for icm in emodel.ion_channel_models:
        suffix = icm.nmodl_suffix
        name = icm.name
        if suffix and name:
            mapping[suffix] = name

    return mapping


def _build_channel_entity_id_mapping(emodel: EModel) -> dict[str, str | None]:
    """Build mapping from channel name to entity ID.

    Example: {'CaDynamics_DC0': '3d371a7e-...', 'pas': None}
    """
    mapping = {}
    if not emodel.ion_channel_models:
        return mapping

    for icm in emodel.ion_channel_models:
        name = icm.name
        entity_id = str(icm.id) if hasattr(icm, "id") and icm.id else None
        if name:
            mapping[name] = entity_id

    return mapping


def _build_channel_section_list_mapping(
    optimized_params: list[MechanismVariable],
    suffix_to_channel_name: dict[str, str],
    channel_entity_ids: dict[str, str | None],
    known_suffixes: list[str],
) -> ChannelSectionListMapping:
    """Build mapping of ion channel names to their info from emodel JSON.

    This shows where each ion channel appears in the optimized parameters
    and includes entity IDs from metadata.
    """
    channel_to_sections: dict[str, set[str]] = {}

    for param in optimized_params:
        # Extract suffix for both RANGE and GLOBAL variables
        suffix = _extract_channel_suffix(param.neuron_variable, known_suffixes)
        if suffix:
            channel_name = suffix_to_channel_name.get(suffix, suffix)
            if channel_name not in channel_to_sections:
                channel_to_sections[channel_name] = set()
            # Only add section_list for RANGE variables
            if param.variable_type == "RANGE":
                channel_to_sections[channel_name].add(param.section_list)

    # Convert sets to sorted lists and add entity IDs
    return ChannelSectionListMapping(
        channel_to_section_lists={
            channel: ChannelInfo(
                section_lists=sorted(sections),
                entity_id=channel_entity_ids.get(channel),
            )
            for channel, sections in channel_to_sections.items()
        }
    )


def _infer_section_lists_for_ion_channel_vars(
    ion_channel_vars: list[MechanismVariable],
    optimized_keys: set[tuple[str, str]],
    channel_mapping: ChannelSectionListMapping,
    suffix_to_channel_name: dict[str, str],
    known_suffixes: list[str],
) -> list[MechanismVariable]:
    """Infer section lists for ion channel variables not in emodel JSON.

    For RANGE variables: use section lists from channel mapping
    For GLOBAL variables: keep empty section_list
    """
    result = []

    for var in ion_channel_vars:
        # Skip if this exact (variable, section_list) combo exists in emodel JSON
        if (var.neuron_variable, var.section_list) in optimized_keys:
            continue

        # For GLOBAL variables, keep empty section_list
        if var.variable_type == "GLOBAL":
            result.append(
                MechanismVariable(
                    neuron_variable=var.neuron_variable,
                    section_list="",  # Empty for GLOBAL
                    units=var.units,
                    limits=var.limits,
                    variable_type="GLOBAL",
                )
            )
            continue

        # For RANGE variables, infer section lists from channel mapping
        suffix = _extract_channel_suffix(var.neuron_variable, known_suffixes)
        if suffix and suffix in suffix_to_channel_name:
            channel_name = suffix_to_channel_name[suffix]
            if channel_name in channel_mapping.channel_to_section_lists:
                channel_info = channel_mapping.channel_to_section_lists[channel_name]
                result.extend(
                    MechanismVariable(
                        neuron_variable=var.neuron_variable,
                        section_list=section_list,
                        units=var.units,
                        limits=var.limits,
                        variable_type="RANGE",
                    )
                    for section_list in channel_info.section_lists
                    if (var.neuron_variable, section_list) not in optimized_keys
                )

    return result


def _create_mechanism_variable_from_ion_channel(
    var_name: str,
    var_units: str,
    suffix: str,
    variable_type: str,
) -> MechanismVariable | None:
    """Create a MechanismVariable from ion channel metadata.

    Filters out variables starting with 'i' (ionic currents).
    Adds limits [0,10] for variables starting with 'g'.
    Note: section_list will be inferred later based on channel mapping.
    """
    # Filter out variables starting with 'i' (ionic currents)
    if var_name.startswith("i"):
        return None

    neuron_variable = f"{var_name}_{suffix}"
    limits = [0.0, 10.0] if neuron_variable.startswith("g") else None

    return MechanismVariable(
        neuron_variable=neuron_variable,
        section_list="all",  # Placeholder, will be replaced during inference
        units=var_units if isinstance(var_units, str) else "",
        limits=limits,
        variable_type=variable_type,
    )


def _process_neuron_block_entries(
    entries: list[dict],
    suffix: str,
    variable_type: str,
) -> list[MechanismVariable]:
    """Process RANGE or GLOBAL entries from a neuron block."""
    variables = []
    for entry in entries:
        for var_name, var_units in entry.items():
            var = _create_mechanism_variable_from_ion_channel(
                var_name, var_units, suffix, variable_type
            )
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
            variables.extend(_process_neuron_block_entries(neuron_block.range, suffix, "RANGE"))

        if neuron_block.global_:
            variables.extend(_process_neuron_block_entries(neuron_block.global_, suffix, "GLOBAL"))

    return variables
