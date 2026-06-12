from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from entitysdk import Client, models
from entitysdk.types import DerivationType

from obi_one.utils.circuit_registration import register_circuit
from obi_one.utils.circuit_registration.links import CustomizationType


def upload_customized_circuit(
    client: Client,
    name: str,
    description: str,
    circuit_path: str | Path,
    customized_from: models.Circuit | UUID,
    customization_type: CustomizationType,
    *,
    brain_region_override: models.BrainRegion | None = None,
    subject_override: models.Subject | None = None,
    contact_email: str | None = None,
    dry_run: bool = False,
) -> models.Circuit | None:
    """Upload function for customized circuits.

    Args:
        client: The entitycore SDK client.
        name: Name of the customized circuit.
        description: Description of the customization.
        circuit_path: Path to the customized circuit.
        customized_from: Parent circuit entity or its UUID.
        customization_type: Type of customization applied.
        brain_region_override: Override brain region (defaults to parent circuit's).
        subject_override: Override subject (defaults to parent circuit's).
        contact_email: Contact email address (optional).
        dry_run: If True, perform a dry run without registering.

    Returns:
        The registered circuit entity, or None if dry_run is True.
    """
    # Get customized_from entity
    if isinstance(customized_from, UUID):
        customized_from = client.get_entity(entity_id=customized_from, entity_type=models.Circuit)

    # Resolve brain_region and subject (use overrides or fall back to parent)
    brain_region = brain_region_override or customized_from.brain_region
    subject = subject_override or customized_from.subject

    if brain_region is None:
        msg = f"Circuit '{customized_from.name}' has no brain_region set and none provided!"
        raise ValueError(msg)
    if subject is None:
        msg = f"Circuit '{customized_from.name}' has no subject set and none provided!"
        raise ValueError(msg)

    # Resolve atlas from parent circuit
    atlas = None
    if customized_from.atlas_id is not None:
        atlas = client.get_entity(entity_id=customized_from.atlas_id, entity_type=models.BrainAtlas)

    # Add description prefix
    descr_prefix = f"Customization of circuit '{customized_from.name}': "
    description = descr_prefix + description

    # Run registration
    return register_circuit(
        client=client,
        circuit_path=circuit_path,
        name=name,
        description=description,
        build_category=customized_from.build_category,
        brain_region=brain_region,
        subject=subject,
        target_simulator=customized_from.target_simulator,
        contact_email=contact_email,
        experiment_date=datetime.now(UTC),
        license=customized_from.license,
        atlas=atlas,
        root=customized_from.root_circuit_id or customized_from.id,
        parent=customized_from,
        derivation_type=DerivationType.circuit_customization,
        derivation_label=customization_type.value,
        dry_run=dry_run,
    )
