"""Register the Brian2 point-neuron circuit produced from EM connectivity as a Circuit entity."""

import logging
from pathlib import Path

from entitysdk import Client, models
from entitysdk.models import EMDenseReconstructionDataset
from entitysdk.types import CircuitBuildCategory, TargetSimulator

from obi_one.utils.circuit_registration import register_circuit_from_metadata

L = logging.getLogger(__name__)

# How many pt_root_ids to embed in the circuit name before summarising the remainder.
_MAX_NAMED_IDS = 3


def _hierarchy_name(db_client: Client, source_dataset: EMDenseReconstructionDataset) -> str:
    """Resolve the brain region hierarchy name from the dataset's brain region."""
    hierarchy = db_client.get_entity(
        entity_id=source_dataset.brain_region.hierarchy_id,  # ty:ignore[invalid-argument-type, unresolved-attribute]
        entity_type=models.BrainRegionHierarchy,
    )
    return hierarchy.name  # ty:ignore[unresolved-attribute]


def circuit_metadata(
    db_client: Client,
    source_dataset: EMDenseReconstructionDataset,
    point_pt_root_ids: list[int],
    virtual_count: int,
) -> dict:
    """Build the circuit metadata dict, sourcing linked entities from the EM dataset.

    The species, subject, brain region and brain region hierarchy come from the EM dense
    reconstruction dataset the meshes originate from.
    """
    n_neurons = len(point_pt_root_ids)
    short_ids = "-".join(str(pt_root_id) for pt_root_id in point_pt_root_ids[:_MAX_NAMED_IDS])
    suffix = "" if n_neurons <= _MAX_NAMED_IDS else f"-and-{n_neurons - _MAX_NAMED_IDS}-more"

    experiment_date = None
    if source_dataset.experiment_date is not None:
        experiment_date = source_dataset.experiment_date.strftime("%d.%m.%Y")

    return {
        "name": f"PointNeuronCircuitFromEM-{short_ids}{suffix}",
        "description": (
            f"Brian2 point-neuron (LIF) circuit of {len(point_pt_root_ids)} neurons "
            f"(pt_root_ids: {point_pt_root_ids}) with {virtual_count} external (virtual) "
            f"afferent neurons. Connectivity is resolved from the EM dense reconstruction "
            f"dataset '{source_dataset.name}'. Neuronal and synaptic parameters are "
            f"placeholders borrowed from the Drosophila brain model."
        ),
        "build_category": CircuitBuildCategory.computational_model,
        "target_simulator": TargetSimulator.Brian2,
        # Override scale; None lets it be inferred from the circuit.
        "scale_override": None,
        # --- Linked entities, sourced from the EM dense reconstruction dataset ---
        "species": source_dataset.subject.species.name,  # ty:ignore[unresolved-attribute]
        "subject": source_dataset.subject.name,  # ty:ignore[unresolved-attribute]
        "brain_region_hierarchy": _hierarchy_name(db_client, source_dataset),
        "brain_region": source_dataset.brain_region.name,  # ty:ignore[unresolved-attribute]
        # --- Optional metadata ---
        "root": None,
        "parent": None,
        "derivation_type": None,
        "license": (
            source_dataset.license.label if source_dataset.license is not None else None  # ty:ignore[unresolved-attribute]
        ),
        "published_in": None,
        "contact": None,
        "experiment_date": experiment_date,
    }


def register_point_neuron_circuit(
    db_client: Client,
    circuit_path: Path,
    source_dataset: EMDenseReconstructionDataset,
    point_pt_root_ids: list[int],
    virtual_count: int,
) -> str | None:
    """Register the Brian2 SONATA circuit as a Circuit entity.

    Uses obi_one's ``register_circuit_from_metadata``, which resolves the linked entities
    (species, subject, brain region, brain region hierarchy, license) from the metadata,
    validates the SONATA circuit, computes counts/scale, and registers the circuit and its
    assets. Returns the registered circuit id (or the id of a pre-existing circuit with the
    same name).
    """
    metadata = circuit_metadata(db_client, source_dataset, point_pt_root_ids, virtual_count)

    existing = db_client.search_entity(
        entity_type=models.Circuit, query={"name": metadata["name"]}
    ).all()
    if existing:
        L.info("Circuit %s already registered (%s)", metadata["name"], existing[0].id)
        return str(existing[0].id)

    registered = register_circuit_from_metadata(
        client=db_client,
        circuit_metadata=metadata,
        circuit_path=str(circuit_path),
    )
    if registered is None:
        return None
    L.info("Registered circuit: %s (%s)", metadata["name"], registered.id)  # ty:ignore[unresolved-attribute]
    return str(registered.id)  # ty:ignore[unresolved-attribute]
