"""Registration of validation outcomes as ValidationResult entities.

Handles:
- Deduplication (skip if a ValidationResult with same name already exists for this entity)
- Entity creation via entitysdk
- Figure/asset upload
- Validation details upload
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from entitysdk import Client
from entitysdk.models import ValidationResult
from entitysdk.types import AssetLabel, ContentType

from bluecellulab.validation.base import ValidationOutcome

logger = logging.getLogger(__name__)


@dataclass
class RegisteredResult:
    """A ValidationResult that was successfully registered on the platform.

    Attributes:
        entity_id: The platform-assigned ID for the registered entity.
        outcome: The original validation outcome.
        skipped: True if registration was skipped due to deduplication.
    """

    entity_id: str | None
    outcome: ValidationOutcome
    skipped: bool = False


def _already_registered(client: Client, name: str, validated_entity_id: str) -> bool:
    """Check if a ValidationResult with this name already exists for the entity."""
    iterator = client.search_entity(
        entity_type=ValidationResult,
        query={"name": name, "validated_entity_id": validated_entity_id},
    )
    return iterator.first() is not None


def _upload_figures(
    client: Client,
    entity_id: str,
    figures: list[Path],
) -> None:
    """Upload figure files as assets on the ValidationResult entity."""
    for fig_path in figures:
        fig_path = Path(fig_path)
        if not fig_path.exists():
            logger.warning(f"Figure not found, skipping: {fig_path}")
            continue

        if fig_path.suffix == ".pdf":
            content_type = ContentType.application_pdf
        elif fig_path.suffix == ".png":
            content_type = ContentType.image_png
        else:
            logger.warning(f"Unsupported figure format, skipping: {fig_path}")
            continue

        client.upload_file(
            entity_id=entity_id,
            entity_type=ValidationResult,
            file_path=fig_path,
            file_content_type=content_type,
            asset_label=AssetLabel.validation_result_figure,
        )


def _upload_details(
    client: Client,
    entity_id: str,
    name: str,
    details: str,
    out_dir: Path,
) -> None:
    """Upload validation details as a text file asset."""
    if not details:
        return

    details_fname = f"{name.replace(' ', '')}_validation_details.txt"
    details_path = Path(out_dir) / details_fname
    details_path.write_text(details)

    client.upload_file(
        entity_id=entity_id,
        entity_type=ValidationResult,
        file_path=details_path,
        file_content_type=ContentType.text_plain,
        asset_label=AssetLabel.validation_result_details,
    )


def register_outcome(
    client: Client,
    outcome: ValidationOutcome,
    validated_entity_id: str,
    out_dir: Path | None = None,
    skip_if_exists: bool = True,
) -> RegisteredResult:
    """Register a single ValidationOutcome as a ValidationResult entity.

    Args:
        client: entitysdk Client instance.
        outcome: The validation outcome to register.
        validated_entity_id: The entity ID that was validated.
        out_dir: Directory for writing temporary detail files.
        skip_if_exists: If True, skip registration when a result already exists.

    Returns:
        A RegisteredResult indicating success or skip.
    """
    if skip_if_exists and _already_registered(client, outcome.name, validated_entity_id):
        logger.info(
            f"ValidationResult '{outcome.name}' already exists for entity "
            f"{validated_entity_id}. Skipping."
        )
        return RegisteredResult(entity_id=None, outcome=outcome, skipped=True)

    # Create the ValidationResult entity
    validation_result = ValidationResult(
        name=outcome.name,
        passed=outcome.passed,
        validated_entity_id=validated_entity_id,
        description=outcome.details,
    )
    registered = client.register_entity(entity=validation_result)
    entity_id = str(registered.id)

    # Upload figures
    _upload_figures(client, entity_id, outcome.figures)

    # Upload details
    if out_dir:
        _upload_details(client, entity_id, outcome.name, outcome.details, out_dir)

    logger.info(
        f"Registered ValidationResult '{outcome.name}' "
        f"(id={entity_id}, passed={outcome.passed})"
    )

    return RegisteredResult(entity_id=entity_id, outcome=outcome, skipped=False)


def register_outcomes(
    client: Client,
    outcomes: list[ValidationOutcome],
    validated_entity_id: str,
    out_dir: Path | None = None,
    skip_if_exists: bool = True,
) -> list[RegisteredResult]:
    """Register multiple validation outcomes.

    Args:
        client: entitysdk Client instance.
        outcomes: List of validation outcomes to register.
        validated_entity_id: The entity ID that was validated.
        out_dir: Directory for writing temporary detail files.
        skip_if_exists: If True, skip registration when a result already exists.

    Returns:
        List of RegisteredResult objects.
    """
    results = []
    for outcome in outcomes:
        try:
            result = register_outcome(
                client, outcome, validated_entity_id, out_dir, skip_if_exists
            )
            results.append(result)
        except Exception:
            logger.exception(
                f"Failed to register ValidationResult '{outcome.name}' "
                f"for entity {validated_entity_id}"
            )
            results.append(RegisteredResult(entity_id=None, outcome=outcome, skipped=False))
    return results
