"""Registration of test results as ValidationResult entities.

Handles:
- Deduplication (skip if a ValidationResult with same name already exists for this entity)
- Entity creation via entitysdk
- Figure/asset upload
- Validation details upload
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from bluecellulab.validation.base import TestResult
from entitysdk import Client
from entitysdk.models import ValidationResult
from entitysdk.types import AssetLabel, ContentType

logger = logging.getLogger(__name__)


@dataclass
class RegisteredResult:
    """A ValidationResult that was successfully registered on the platform.

    Attributes:
        entity_id: The platform-assigned ID for the registered entity.
        test_result: The original test result.
        skipped: True if registration was skipped due to deduplication.
    """

    entity_id: str | None
    test_result: TestResult
    skipped: bool = False


def _already_registered(client: Client, name: str, validated_entity_id: UUID) -> bool:
    """Check if a ValidationResult with this name already exists for the entity."""
    iterator = client.search_entity(
        entity_type=ValidationResult,
        query={"name": name, "validated_entity_id": validated_entity_id},
    )
    return iterator.first() is not None


def _upload_figures(
    client: Client,
    entity_id: UUID,
    figures: list[Path],
) -> None:
    """Upload figure files as assets on the ValidationResult entity."""
    for fig_path in figures:
        resolved_path = Path(fig_path)
        if not resolved_path.exists():
            logger.warning("Figure not found, skipping: %s", resolved_path)
            continue

        if resolved_path.suffix == ".pdf":
            content_type = ContentType.application_pdf
        elif resolved_path.suffix == ".png":
            content_type = ContentType.image_png
        else:
            logger.warning("Unsupported figure format, skipping: %s", resolved_path)
            continue

        client.upload_file(
            entity_id=entity_id,
            entity_type=ValidationResult,
            file_path=resolved_path,
            file_content_type=content_type,
            asset_label=AssetLabel.validation_result_figure,
        )


def _upload_details(
    client: Client,
    entity_id: UUID,
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
    test_result: TestResult,
    validated_entity_id: str,
    *,
    out_dir: Path | None = None,
    skip_if_exists: bool = True,
) -> RegisteredResult:
    """Register a single TestResult as a ValidationResult entity.

    Args:
        client: entitysdk Client instance.
        test_result: The test result to register.
        validated_entity_id: The entity ID that was validated.
        out_dir: Directory for writing temporary detail files.
        skip_if_exists: If True, skip registration when a result already exists.

    Returns:
        A RegisteredResult indicating success or skip.
    """
    validated_entity_uuid = UUID(validated_entity_id)
    if skip_if_exists and _already_registered(client, test_result.name, validated_entity_uuid):
        logger.info(
            "ValidationResult '%s' already exists for entity %s. Skipping.",
            test_result.name,
            validated_entity_id,
        )
        return RegisteredResult(entity_id=None, test_result=test_result, skipped=True)

    # Create the ValidationResult entity
    validation_result = ValidationResult(
        name=test_result.name,
        passed=test_result.passed,
        validated_entity_id=validated_entity_uuid,
        description=test_result.details,
    )
    registered = client.register_entity(entity=validation_result)
    if registered.id is None:
        raise RuntimeError
    entity_id = str(registered.id)

    # Upload figures
    _upload_figures(client, registered.id, test_result.figures)

    # Upload details
    if out_dir:
        _upload_details(client, registered.id, test_result.name, test_result.details, out_dir)

    logger.info(
        "Registered ValidationResult '%s' (id=%s, passed=%s)",
        test_result.name,
        entity_id,
        test_result.passed,
    )

    return RegisteredResult(entity_id=entity_id, test_result=test_result, skipped=False)


def register_outcomes(
    client: Client,
    test_results: list[TestResult],
    validated_entity_id: str,
    *,
    out_dir: Path | None = None,
    skip_if_exists: bool = True,
) -> list[RegisteredResult]:
    """Register multiple test results.

    Args:
        client: entitysdk Client instance.
        test_results: List of test results to register.
        validated_entity_id: The entity ID that was validated.
        out_dir: Directory for writing temporary detail files.
        skip_if_exists: If True, skip registration when a result already exists.

    Returns:
        List of RegisteredResult objects.
    """
    results = []
    for test_result in test_results:
        try:
            result = register_outcome(
                client,
                test_result,
                validated_entity_id,
                out_dir=out_dir,
                skip_if_exists=skip_if_exists,
            )
            results.append(result)
        except Exception:
            logger.exception(
                "Failed to register ValidationResult '%s' for entity %s",
                test_result.name,
                validated_entity_id,
            )
            results.append(RegisteredResult(entity_id=None, test_result=test_result, skipped=False))
    return results
