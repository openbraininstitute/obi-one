"""entitycore registration for circuits built by sonata-builder."""

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from entitysdk import types
from entitysdk.client import Client
from entitysdk.models import Circuit

from obi_one.core.exception import OBIONEError
from obi_one.db_sdk.registration.circuit.register import register_circuit
from obi_one.db_sdk.registration.circuit.resolve import (
    check_hierarchy_species,
    get_brain_region,
    get_brain_region_hierarchy,
    get_license,
    get_subject,
)

if TYPE_CHECKING:
    from obi_one.scientific.tasks.circuit_build.config import (
        OrganoidCircuitBuildSingleConfig,
    )

L = logging.getLogger(__name__)


def register_built_circuit(
    config: "OrganoidCircuitBuildSingleConfig",
    db_client: Client,
    circuit_dir: Path,
) -> Circuit:
    """Register a built SONATA circuit in entitycore.

    Resolves subject / brain region / license from the registration block, then
    registers the circuit (folder asset, validation, additional assets, and
    derivation links to the input MEModels).

    Args:
        config: The single build configuration.
        db_client: entitysdk client.
        circuit_dir: Directory containing the built circuit (with circuit_config.json).

    Returns:
        The registered Circuit entity.
    """
    registration = config.registration

    circuit_metadata = {
        "subject": registration.subject_name,
        "species": config.experiment.species,
        "brain_region": registration.brain_region_name,
        "brain_region_hierarchy": registration.brain_region_hierarchy_name,
        "license": registration.license_label,
    }

    subject = get_subject(db_client, circuit_metadata)
    hierarchy = get_brain_region_hierarchy(db_client, circuit_metadata)
    check_hierarchy_species(hierarchy, subject)
    brain_region = get_brain_region(db_client, circuit_metadata, hierarchy)
    license_entity = get_license(db_client, circuit_metadata)

    experiment_date = None
    if registration.experiment_date:
        experiment_date = datetime.fromisoformat(registration.experiment_date)

    circuit = register_circuit(
        db_client,
        circuit_dir / "circuit_config.json",
        name=config.campaign_name,
        description=config.campaign_description,
        build_category=types.CircuitBuildCategory.computational_model,
        brain_region=brain_region,
        subject=subject,
        target_simulator=types.TargetSimulator.NEURON,
        contact_email=registration.contact_email,
        experiment_date=experiment_date,
        license=license_entity,
        authorized_public=False,
    )
    if circuit is None:
        msg = "Circuit registration did not return an entity."
        raise OBIONEError(msg)
    L.info("Registered circuit %s (ID %s)", circuit.name, circuit.id)
    return circuit
