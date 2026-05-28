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
from obi_one.scientific.library.circuit_metrics import TemporaryAsset
from obi_one.scientific.library.emodel_parameters import get_mechanism_variables_for_emodel
from obi_one.scientific.library.memodel_circuit import (
    IonChannelVariables,
    MechanismVariableDetail,
    _build_mechanism_variables_by_ion_channel_response,
)

if TYPE_CHECKING:
    import entitysdk.client

    from obi_one.scientific.blocks.neuron_sets.base import AbstractNeuronSet

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


def get_circuit_node_ids(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    neuron_set: AbstractNeuronSet,
    population: str | None = None,
) -> tuple[str, list[int]]:
    """Resolve a neuron set to node IDs for a circuit.

    Args:
        db_client: entitysdk client.
        circuit_id: Circuit entity ID.
        neuron_set: Neuron set to resolve.
        population: Node population name. Defaults to circuit's default.

    Returns:
        Tuple of (population_name, node_ids).
    """
    circuit_entity, asset_id = _get_circuit_asset(db_client, circuit_id)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_config_path = Path(temp_dir) / "circuit_config.json"
        db_client.fetch_file(
            entity_id=UUID(circuit_id),
            entity_type=Circuit,
            asset_id=asset_id,
            output_path=temp_config_path,
            asset_path=Path("circuit_config.json"),
            strategy=FetchFileStrategy.link_or_download,
        )

        obi_circuit = ObiCircuit(name=circuit_entity.name or circuit_id, path=str(temp_config_path))

        if population is None:
            population = obi_circuit.default_population_name

        node_ids = neuron_set.get_neuron_ids(obi_circuit, population).tolist()

    return population, node_ids


def get_model_template_for_nodes(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    population: str,
    node_ids: list[int],
    asset_id: UUID,
) -> dict[int, str]:
    """Read model_template property for specific node IDs.

    Args:
        db_client: entitysdk client.
        circuit_id: Circuit entity ID.
        population: Node population name.
        node_ids: List of node IDs to read model_template for.
        asset_id: The sonata_circuit directory asset ID.

    Returns:
        Dict mapping node_id to model_template value.

    Raises:
        ValueError: If model_template property is not available.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_config_path = Path(temp_dir) / "circuit_config.json"
        db_client.fetch_file(
            entity_id=UUID(circuit_id),
            entity_type=Circuit,
            asset_id=asset_id,
            output_path=temp_config_path,
            asset_path=Path("circuit_config.json"),
            strategy=FetchFileStrategy.link_or_download,
        )

        snap_circuit = SnapCircuit(temp_config_path)
        nodes_h5_path = snap_circuit.nodes[population].h5_filepath
        remote_path = Path(nodes_h5_path).relative_to(temp_dir)

        with TemporaryAsset(remote_path, db_client, circuit_id, str(asset_id)) as nodes_file:
            pop_obj = NodeStorage(nodes_file).open_population(population)

            if "model_template" not in pop_obj.attribute_names:
                msg = (
                    f"Property 'model_template' not found in population"
                    f" '{population}' of circuit {circuit_id}."
                    f" Available: {list(pop_obj.attribute_names)}"
                )
                raise ValueError(msg)

            templates = pop_obj.get_attribute("model_template", node_ids)

    return dict(zip(node_ids, templates, strict=True))


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
        if deriv.label:
            label_to_emodel_id[deriv.label] = str(deriv.used.id)
    return label_to_emodel_id


def _match_templates_to_emodels(
    node_to_template: dict[int, str],
    label_to_emodel_id: dict[str, str],
) -> tuple[dict[int, str], set[str]]:
    """Match node model_template values to emodel IDs via derivation labels.

    Returns:
        Tuple of (node_id_to_emodel, unmatched_templates).
    """
    node_id_to_emodel: dict[int, str] = {}
    unmatched_templates: set[str] = set()
    for nid, template in node_to_template.items():
        if template in label_to_emodel_id:
            node_id_to_emodel[nid] = label_to_emodel_id[template]
        else:
            unmatched_templates.add(template)
    return node_id_to_emodel, unmatched_templates


def _build_emodel_groups(
    db_client: entitysdk.client.Client,
    node_id_to_emodel: dict[int, str],
    label_to_emodel_id: dict[str, str],
) -> dict[str, dict]:
    """Group nodes by emodel and fetch mechanism variables for each."""
    emodel_to_nodes: dict[str, list[int]] = {}
    for nid, emodel_id in node_id_to_emodel.items():
        emodel_to_nodes.setdefault(emodel_id, []).append(nid)

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


def _resolve_population_and_node_ids(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    circuit_entity: Circuit,
    asset_id: UUID,
    neuron_set: AbstractNeuronSet | None,
    node_ids: list[int] | None,
    population: str | None,
) -> tuple[str, list[int]]:
    """Resolve population name and node IDs from inputs."""
    if node_ids is not None:
        if population is None:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_config_path = Path(temp_dir) / "circuit_config.json"
                db_client.fetch_file(
                    entity_id=UUID(circuit_id),
                    entity_type=Circuit,
                    asset_id=asset_id,
                    output_path=temp_config_path,
                    asset_path=Path("circuit_config.json"),
                    strategy=FetchFileStrategy.link_or_download,
                )
                obi_circuit = ObiCircuit(
                    name=circuit_entity.name or circuit_id, path=str(temp_config_path)
                )
                population = obi_circuit.default_population_name
        return population, node_ids

    if neuron_set is None:
        msg = "Either neuron_set or node_ids must be provided."
        raise ValueError(msg)
    return get_circuit_node_ids(db_client, circuit_id, neuron_set, population)


def get_circuit_manipulation_properties(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    neuron_set: AbstractNeuronSet | None = None,
    node_ids: list[int] | None = None,
    population: str | None = None,
) -> dict:
    """Get neuronal manipulation properties for a circuit + neuron set.

    Accepts either neuron_set or node_ids (node_ids takes precedence).

    Returns the intersection (common) of mechanism variables across all emodels
    in the selection. The response shape matches the MEModel response so the
    frontend can render both identically.

    Args:
        db_client: entitysdk client.
        circuit_id: Circuit entity ID.
        neuron_set: Neuron set to resolve.
        node_ids: Direct list of node IDs (for debugging/direct calls).
        population: Node population name. Defaults to circuit's default.

    Returns:
        Dict with entity_type, population, mechanism_variables_by_ion_channel,
        and optional warnings.
    """
    circuit_entity, asset_id = _get_circuit_asset(db_client, circuit_id)

    # 1. Resolve node IDs
    resolved_population, node_ids = _resolve_population_and_node_ids(
        db_client, circuit_id, circuit_entity, asset_id, neuron_set, node_ids, population
    )

    # 2. Read model_template per node
    node_to_template = get_model_template_for_nodes(
        db_client, circuit_id, resolved_population, node_ids, asset_id
    )

    # 3. Fetch derivations and match to emodels
    label_to_emodel_id = _fetch_emodel_derivation_mapping(db_client, circuit_id)
    node_id_to_emodel, unmatched_templates = _match_templates_to_emodels(
        node_to_template, label_to_emodel_id
    )

    # 4. Build per-emodel groups (internal step)
    emodel_groups = _build_emodel_groups(db_client, node_id_to_emodel, label_to_emodel_id)

    # 5. Compute intersection of mechanism variables across all emodels
    common_vars = _compute_common_mechanism_variables(emodel_groups)

    # 6. Build response
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
        "population": resolved_population,
        "mechanism_variables_by_ion_channel": common_vars,
        "warnings": warnings,
    }
