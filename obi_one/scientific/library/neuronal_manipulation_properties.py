"""Neuronal manipulation properties for circuits.

Provides logic to:
- Resolve a neuron set to node IDs for a circuit.
- Read model_template property for selected node IDs.
- Match model_template values to emodel derivations.
- Fetch mechanism variables for each unique emodel.
- Return grouped response for the frontend.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from bluepysnap import Circuit as SnapCircuit
from entitysdk.models.circuit import Circuit
from entitysdk.types import DerivationType, FetchFileStrategy
from libsonata import NodeStorage

from obi_one.scientific.library.circuit import Circuit as ObiCircuit
from obi_one.scientific.library.circuit_metrics import TemporaryAsset
from obi_one.scientific.library.emodel_parameters import get_mechanism_variables_for_emodel
from obi_one.scientific.library.memodel_circuit import (
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

    return circuit_entity, directory_assets[0].id


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

        obi_circuit = ObiCircuit(name=circuit_entity.name, path=str(temp_config_path))

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
    derivations = db_client.get_entity_derivations(
        entity_id=UUID(circuit_id),
        entity_type=Circuit,
        derivation_type=DerivationType.emodel_circuit,
    )
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


def get_circuit_manipulation_properties(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    neuron_set: AbstractNeuronSet | None = None,
    node_ids: list[int] | None = None,
    population: str | None = None,
) -> dict:
    """Get neuronal manipulation properties for a circuit + neuron set.

    Accepts either neuron_set or node_ids (node_ids takes precedence).

    Args:
        db_client: entitysdk client.
        circuit_id: Circuit entity ID.
        neuron_set: Neuron set to resolve.
        node_ids: Direct list of node IDs (for debugging/direct calls).
        population: Node population name. Defaults to circuit's default.

    Returns:
        Dict with entity_type, population, node_ids, node_id_to_emodel,
        emodel_groups, and optional warnings.
    """
    circuit_entity, asset_id = _get_circuit_asset(db_client, circuit_id)

    # 1. Resolve node IDs
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
                obi_circuit = ObiCircuit(name=circuit_entity.name, path=str(temp_config_path))
                population = obi_circuit.default_population_name
        resolved_population = population
    else:
        if neuron_set is None:
            msg = "Either neuron_set or node_ids must be provided."
            raise ValueError(msg)
        resolved_population, node_ids = get_circuit_node_ids(
            db_client, circuit_id, neuron_set, population
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

    # 4. Build emodel groups with mechanism variables
    emodel_groups = _build_emodel_groups(db_client, node_id_to_emodel, label_to_emodel_id)

    # 5. Build response
    warnings = None
    if unmatched_templates:
        warnings = [
            f"No derivation found for model_template: {t}" for t in sorted(unmatched_templates)
        ]

    return {
        "entity_type": "circuit",
        "population": resolved_population,
        "node_ids": sorted(node_ids),
        "node_id_to_emodel": {str(k): v for k, v in node_id_to_emodel.items()},
        "emodel_groups": emodel_groups,
        "warnings": warnings,
    }
