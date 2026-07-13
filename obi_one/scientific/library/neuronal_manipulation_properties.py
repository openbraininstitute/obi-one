"""Neuronal manipulation properties for circuits.

Provides logic to:
- Resolve a neuron set to node IDs for a circuit.
- Read model_template property for selected node IDs.
- Match model_template values to emodel derivations.
- Fetch mechanism variables for each unique emodel.
- Compute the intersection (common) of mechanism variables across all emodels.
- Return a flat response matching the MEModel response shape.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from bluepysnap import Circuit as SnapCircuit
from entitysdk.models import Derivation as DerivationModel
from entitysdk.models.circuit import Circuit
from entitysdk.types import FetchFileStrategy
from libsonata import NodeStorage

from obi_one.scientific.library.circuit import Circuit as ObiCircuit
from obi_one.scientific.library.emodel_parameters import get_mechanism_variables_for_emodel
from obi_one.scientific.library.entity_property_types import CircuitMappedProperties
from obi_one.scientific.library.memodel_circuit import (
    IonChannelVariables,
    MechanismVariableDetail,
    _build_mechanism_variables_by_ion_channel_response,
)

if TYPE_CHECKING:
    import entitysdk.client

    from obi_one.scientific.blocks.neuron_sets.base import NeuronSet

L = logging.getLogger(__name__)


def _get_circuit_asset(
    db_client: entitysdk.client.Client,
    circuit_id: str,
) -> tuple[Circuit, UUID]:
    """Get circuit entity and its sonata_circuit directory asset ID."""
    circuit_entity = db_client.get_entity(
        entity_id=UUID(circuit_id),
        entity_type=Circuit,
    )

    directory_assets = [
        a for a in circuit_entity.assets if a.is_directory and a.label.value == "sonata_circuit"
    ]
    if len(directory_assets) != 1:
        msg = f"Circuit {circuit_id} must have exactly one sonata_circuit directory asset."
        raise ValueError(msg)

    asset_id = directory_assets[0].id
    if asset_id is None:
        msg = f"Circuit {circuit_id} sonata_circuit asset has no ID."
        raise ValueError(msg)

    return circuit_entity, asset_id


def _stage_file(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    asset_id: UUID,
    temp_dir: Path,
    asset_path: str,
) -> Path:
    """Stage a single file from the circuit's sonata_circuit asset into temp_dir."""
    output_path = temp_dir / asset_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    db_client.fetch_file(
        entity_id=UUID(circuit_id),
        entity_type=Circuit,
        asset_id=asset_id,
        output_path=output_path,
        asset_path=Path(asset_path),
        strategy=FetchFileStrategy.link_or_download,
    )
    return output_path


def _resolve_neuron_set_and_get_templates(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    circuit_entity: Circuit,
    asset_id: UUID,
    neuron_set: NeuronSet,
) -> tuple[list[str], dict[tuple[str, int], str]]:
    """Stage circuit files, resolve neuron set to node IDs, read model_template.

    Stages circuit_config.json, node_sets.json, and the nodes.h5 for each population
    the neuron set spans, then resolves the neuron set and reads model_template
    for the resulting node IDs across all populations.

    Returns:
        Tuple of (population_names, {(population, node_id): model_template}) where
        the template dict is keyed by population-qualified node IDs to avoid
        collisions between populations with overlapping local node IDs.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir).resolve()

        # Stage circuit_config.json
        _stage_file(db_client, circuit_id, asset_id, temp_dir_path, "circuit_config.json")

        # Stage node_sets.json (needed for neuron set resolution)
        try:
            _stage_file(db_client, circuit_id, asset_id, temp_dir_path, "node_sets.json")
        except Exception:  # noqa: BLE001
            L.debug("node_sets.json not available, continuing without it")

        # Load circuit
        config_path = temp_dir_path / "circuit_config.json"
        obi_circuit = ObiCircuit(name=circuit_entity.name or circuit_id, path=str(config_path))

        # Resolve neuron set → node IDs per population (new API)
        ids_per_population: dict[str, list[int]] = neuron_set.get_neuron_ids(obi_circuit)

        if not ids_per_population:
            msg = f"Neuron set resolved to no node IDs for circuit {circuit_id}."
            raise ValueError(msg)

        snap_circuit = SnapCircuit(str(config_path))
        node_to_template: dict[tuple[str, int], str] = {}
        populations: list[str] = []

        for population, node_ids in ids_per_population.items():
            if not node_ids:
                continue

            populations.append(population)

            # Stage the population's nodes.h5
            nodes_h5_resolved = Path(snap_circuit.nodes[population].h5_filepath).resolve()
            nodes_relative = str(nodes_h5_resolved.relative_to(temp_dir_path))
            _stage_file(db_client, circuit_id, asset_id, temp_dir_path, nodes_relative)

            # Read model_template for those node IDs
            nodes_path = temp_dir_path / nodes_relative
            pop_obj = NodeStorage(str(nodes_path)).open_population(population)

            if "model_template" not in pop_obj.attribute_names:
                msg = (
                    f"Property 'model_template' not found in population"
                    f" '{population}' of circuit {circuit_id}."
                    f" Available: {list(pop_obj.attribute_names)}"
                )
                raise ValueError(msg)

            templates = pop_obj.get_attribute("model_template", node_ids)
            node_to_template.update(
                zip(
                    [(population, nid) for nid in node_ids],
                    templates,
                    strict=True,
                )
            )

        if not populations:
            msg = f"Neuron set resolved to no node IDs for circuit {circuit_id}."
            raise ValueError(msg)

    return populations, node_to_template


def get_circuit_node_ids(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    neuron_set: NeuronSet,
) -> dict[str, list[int]]:
    """Resolve a neuron set to node IDs for a circuit.

    Args:
        db_client: entitysdk client.
        circuit_id: Circuit entity ID.
        neuron_set: Neuron set to resolve.

    Returns:
        Dict mapping population name to list of node IDs.
    """
    circuit_entity, asset_id = _get_circuit_asset(db_client, circuit_id)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir).resolve()

        _stage_file(db_client, circuit_id, asset_id, temp_dir_path, "circuit_config.json")
        try:
            _stage_file(db_client, circuit_id, asset_id, temp_dir_path, "node_sets.json")
        except Exception:  # noqa: BLE001
            L.debug("node_sets.json not available, continuing without it")

        config_path = temp_dir_path / "circuit_config.json"
        obi_circuit = ObiCircuit(name=circuit_entity.name or circuit_id, path=str(config_path))

        ids_per_population = neuron_set.get_neuron_ids(obi_circuit)

    return ids_per_population


def _fetch_emodel_derivation_mapping(
    db_client: entitysdk.client.Client,
    circuit_id: str,
) -> dict[str, str]:
    """Fetch emodel_circuit derivations and build label -> emodel_id map."""
    derivations = db_client.search_entity(
        entity_type=DerivationModel,
        query={
            "generated__id": circuit_id,
            "derivation_type": "emodel_circuit",
        },
    ).all()
    label_to_emodel_id: dict[str, str] = {}
    for deriv in derivations:
        if deriv.label and deriv.used:
            label_to_emodel_id[deriv.label] = str(deriv.used.id)
    return label_to_emodel_id


def _match_templates_to_emodels(
    node_to_template: dict[tuple[str, int], str],
    label_to_emodel_id: dict[str, str],
) -> tuple[dict[tuple[str, int], str], set[str]]:
    """Match node model_template values to emodel IDs via derivation labels.

    Returns:
        Tuple of (node_key_to_emodel, unmatched_templates) where node_key is
        a (population, node_id) tuple.
    """
    node_key_to_emodel: dict[tuple[str, int], str] = {}
    unmatched_templates: set[str] = set()
    for key, template in node_to_template.items():
        if template in label_to_emodel_id:
            node_key_to_emodel[key] = label_to_emodel_id[template]
        else:
            unmatched_templates.add(template)
    return node_key_to_emodel, unmatched_templates


def _build_emodel_groups(
    db_client: entitysdk.client.Client,
    node_key_to_emodel: dict[tuple[str, int], str],
    label_to_emodel_id: dict[str, str],
) -> dict[str, dict]:
    """Group nodes by emodel and fetch mechanism variables for each."""
    emodel_to_nodes: dict[str, list[tuple[str, int]]] = {}
    for key, emodel_id in node_key_to_emodel.items():
        emodel_to_nodes.setdefault(emodel_id, []).append(key)

    emodel_groups: dict[str, dict] = {}
    for emodel_id, group_node_ids in emodel_to_nodes.items():
        template = next(label for label, eid in label_to_emodel_id.items() if eid == emodel_id)
        try:
            variables, channel_mapping = get_mechanism_variables_for_emodel(db_client, emodel_id)
            mechanism_vars = _build_mechanism_variables_by_ion_channel_response(
                variables, channel_mapping
            )
        except Exception:  # noqa: BLE001
            L.warning(
                "Failed to get mechanism variables for emodel %s",
                emodel_id,
                exc_info=True,
            )
            mechanism_vars = {}

        emodel_groups[emodel_id] = {
            "node_ids": sorted(group_node_ids),
            "model_template": template,
            "mechanism_variables_by_ion_channel": mechanism_vars,
        }
    return emodel_groups


def _compute_common_mechanism_variables(
    emodel_groups: dict[str, dict],
) -> dict[str, IonChannelVariables]:
    """Compute the intersection of mechanism variables across all emodel groups.

    Returns only channels and variables that are present in ALL emodel groups.
    For limits, takes the most restrictive range (max of lower bounds, min of upper bounds).
    For section_lists, takes the intersection across groups.

    Special case: if there is only one emodel group, returns its full variable set
    with original values preserved.
    """
    if not emodel_groups:
        return {}

    groups = list(emodel_groups.values())

    # Filter out groups that failed to fetch mechanism variables
    groups_with_vars = [g for g in groups if g["mechanism_variables_by_ion_channel"]]
    if not groups_with_vars:
        return {}

    # Single emodel: return its variables directly (no intersection needed)
    if len(groups_with_vars) == 1:
        return groups_with_vars[0]["mechanism_variables_by_ion_channel"]

    # Multiple emodels: compute intersection
    all_channel_sets = [
        set(g["mechanism_variables_by_ion_channel"].keys()) for g in groups_with_vars
    ]
    common_channels = set.intersection(*all_channel_sets)

    if not common_channels:
        return {}

    result: dict[str, IonChannelVariables] = {}
    for channel in sorted(common_channels):
        # Intersect variables for this channel
        all_var_sets = [
            set(g["mechanism_variables_by_ion_channel"][channel].variables.keys())
            for g in groups_with_vars
        ]
        common_vars = set.intersection(*all_var_sets)
        if not common_vars:
            continue

        # Intersect section_lists for this channel
        all_section_lists = [
            set(g["mechanism_variables_by_ion_channel"][channel].section_lists)
            for g in groups_with_vars
        ]
        common_section_lists = sorted(set.intersection(*all_section_lists))
        if not common_section_lists:
            continue

        # Build variables with merged limits
        variables: dict[str, MechanismVariableDetail] = {}
        for var_name in sorted(common_vars):
            all_details = [
                g["mechanism_variables_by_ion_channel"][channel].variables[var_name]
                for g in groups_with_vars
            ]

            # Most restrictive limits
            all_limits = [d.limits for d in all_details if d.limits is not None]
            if all_limits:
                merged_limits: list[float] | None = [
                    max(lim[0] for lim in all_limits),
                    min(lim[1] for lim in all_limits),
                ]
            else:
                merged_limits = None

            variables[var_name] = MechanismVariableDetail(
                units=all_details[0].units,
                limits=merged_limits,
                variable_type=all_details[0].variable_type,
                section_lists_original_values=dict.fromkeys(common_section_lists),
            )

        result[channel] = IonChannelVariables(
            section_lists=common_section_lists,
            entity_id=None,
            variables=variables,
        )

    return result


def get_circuit_manipulation_properties(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    neuron_set: NeuronSet | None = None,
) -> dict:
    """Get neuronal manipulation properties for a circuit + neuron set.

    Two modes:
    1. neuron_set=None: Fast path — use all derivations (no file I/O).
    2. neuron_set provided: Stage files, resolve neuron set, read model_template.

    Returns the intersection (common) of mechanism variables across all emodels
    in the selection.

    Args:
        db_client: entitysdk client.
        circuit_id: Circuit entity ID.
        neuron_set: Neuron set to resolve (may span multiple populations).

    Returns:
        Dict with entity_type, populations, mechanism_variables_by_ion_channel,
        and optional warnings.
    """
    # Fast path: no neuron_set — use all derivations (no file download)
    if neuron_set is None:
        label_to_emodel_id = _fetch_emodel_derivation_mapping(db_client, circuit_id)
        if not label_to_emodel_id:
            return {
                "entity_type": "circuit",
                "populations": None,
                CircuitMappedProperties.MECHANISM_VARIABLES_BY_ION_CHANNEL: {},
                "warnings": ["No emodel_circuit derivations found for this circuit."],
            }
        # Build emodel groups from all derivations (synthetic keys — not needed for intersection)
        node_key_to_emodel = {
            ("__fast__", i): eid for i, eid in enumerate(label_to_emodel_id.values())
        }
        emodel_groups = _build_emodel_groups(db_client, node_key_to_emodel, label_to_emodel_id)
        common_vars = _compute_common_mechanism_variables(emodel_groups)
        return {
            "entity_type": "circuit",
            "populations": None,
            CircuitMappedProperties.MECHANISM_VARIABLES_BY_ION_CHANNEL: common_vars,
            "warnings": None,
        }

    # Accurate path: resolve neuron set to node IDs across all populations
    circuit_entity, asset_id = _get_circuit_asset(db_client, circuit_id)

    resolved_populations, node_to_template = _resolve_neuron_set_and_get_templates(
        db_client,
        circuit_id,
        circuit_entity,
        asset_id,
        neuron_set,
    )

    # Fetch derivations and match to emodels
    label_to_emodel_id = _fetch_emodel_derivation_mapping(db_client, circuit_id)
    node_id_to_emodel, unmatched_templates = _match_templates_to_emodels(
        node_to_template, label_to_emodel_id
    )

    # Build per-emodel groups (internal step)
    emodel_groups = _build_emodel_groups(db_client, node_id_to_emodel, label_to_emodel_id)

    # Compute intersection of mechanism variables across all emodels
    common_vars = _compute_common_mechanism_variables(emodel_groups)

    # Build response
    warnings: list[str] | None = None
    warning_messages: list[str] = []

    if unmatched_templates:
        warning_messages.extend(
            f"No derivation found for model_template: {t}" for t in sorted(unmatched_templates)
        )

    if not common_vars and emodel_groups:
        warning_messages.append(
            "No common mechanism variables found across the selected neurons' emodels."
        )

    if warning_messages:
        warnings = warning_messages

    return {
        "entity_type": "circuit",
        "populations": resolved_populations,
        CircuitMappedProperties.MECHANISM_VARIABLES_BY_ION_CHANNEL: common_vars,
        "warnings": warnings,
    }
