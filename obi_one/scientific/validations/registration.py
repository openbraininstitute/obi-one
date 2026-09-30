"""Registration of test results as ValidationResult entities.

Handles:
- Existing-result behavior (skip or update)
- Duplicate-match detection
- Entity creation and updates via entitysdk
- Figure/asset upload and replacement
- Validation details upload
"""

import logging
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from uuid import UUID

import httpx
from bluecellulab.validation.base import TestResult
from entitysdk import Client
from entitysdk.models import ValidationResult
from entitysdk.types import AssetLabel, ContentType

logger = logging.getLogger(__name__)


class ValidationResultAlreadyExistsError(ValueError):
    """Raised when multiple matching ValidationResults are found."""


class ValidationResultPermissionError(PermissionError):
    """Raised when the user is not authorized to overwrite an existing ValidationResult.

    This typically means the existing result (or one of its assets) is owned by
    another user or a service account, so it cannot be updated or its assets
    replaced with the current credentials.
    """


def _is_forbidden(exc: httpx.HTTPStatusError) -> bool:
    """Return True if the HTTP error is a 403 Forbidden."""
    return exc.response.status_code == HTTPStatus.FORBIDDEN


@dataclass
class RegisteredResult:
    """A ValidationResult that was processed on the platform.

    Attributes:
        entity_id: The platform-assigned ID. For skipped or updated results, this is
            the existing entity ID.
        test_result: The original test result.
        skipped: True if registration was skipped because the result already exists.
        updated: True if an existing result was updated in place.
    """

    entity_id: str | None
    test_result: TestResult
    skipped: bool = False
    updated: bool = False


def _find_existing(
    client: Client,
    name: str,
    validated_entity_id: UUID,
) -> ValidationResult | None:
    """Find the single result matching a validation name and target entity."""
    iterator = client.search_entity(
        entity_type=ValidationResult,
        query={"name": name, "validated_entity_id": validated_entity_id},
    )
    matches = list(iterator.all())
    if len(matches) > 1:
        msg = (
            f"Multiple ValidationResults named {name!r} exist for "
            f"validated entity {validated_entity_id}; refusing to choose one."
        )
        raise ValidationResultAlreadyExistsError(msg)
    return matches[0] if matches else None


def _result_id(validation_result: ValidationResult) -> UUID:
    """Return a result ID or fail if the server returned an invalid entity."""
    if validation_result.id is None:
        msg = "ValidationResult has no platform-assigned ID"
        raise RuntimeError(msg)
    return validation_result.id


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


def _delete_validation_assets(client: Client, entity_id: UUID) -> None:
    """Delete old validation figures and details before uploading replacements."""
    assets = client.get_entity_assets(
        entity_id=entity_id,
        entity_type=ValidationResult,
    ).all()
    replaceable_labels = {
        AssetLabel.validation_result_figure,
        AssetLabel.validation_result_details,
    }
    for asset in assets:
        if asset.label not in replaceable_labels:
            continue
        if asset.id is None:
            msg = "ValidationResult asset has no platform-assigned ID"
            raise RuntimeError(msg)
        client.delete_asset(
            entity_id=entity_id,
            entity_type=ValidationResult,
            asset_id=asset.id,
        )


def _update_existing(
    client: Client,
    existing: ValidationResult,
    test_result: TestResult,
    validated_entity_id: UUID,
    out_dir: Path | None,
) -> UUID:
    """Update a result in place and replace its validation artifacts.

    Raises:
        ValidationResultPermissionError: If the existing result or its assets are
            owned by another user and cannot be updated/replaced (HTTP 403).
    """
    entity_id = _result_id(existing)
    try:
        # ValidationResult only carries name/passed/validated_entity_id. The details
        # text is persisted separately as an asset via _upload_details below, so it is
        # not sent here; the update endpoint rejects unknown fields with a 422.
        client.update_entity(
            entity_id=entity_id,
            entity_type=ValidationResult,
            attrs_or_entity={
                "name": test_result.name,
                "passed": test_result.passed,
                "validated_entity_id": validated_entity_id,
            },
        )

        # Asset replacement is intentionally explicit. The EntitySDK update operation
        # only patches entity fields and does not remove stale figures or details.
        _delete_validation_assets(client, entity_id)
        _upload_figures(client, entity_id, test_result.figures)
        if out_dir:
            _upload_details(client, entity_id, test_result.name, test_result.details, out_dir)
    except httpx.HTTPStatusError as exc:
        if _is_forbidden(exc):
            msg = (
                f"Not authorized to overwrite ValidationResult '{test_result.name}' "
                f"(id={entity_id}). It is likely owned by another user or a service "
                f"account. Ask the owner to update it, or register the result under an "
                f"entity you own."
            )
            raise ValidationResultPermissionError(msg) from exc
        raise
    return entity_id


def register_outcome(
    client: Client,
    test_result: TestResult,
    validated_entity_id: str,
    *,
    out_dir: Path | None = None,
    overwrite_existing: bool = False,
) -> RegisteredResult:
    """Register or optionally update a single TestResult.

    Args:
        client: entitysdk Client instance.
        test_result: The test result to register.
        validated_entity_id: The entity ID that was validated.
        out_dir: Directory for writing temporary detail files.
        overwrite_existing: If False, skip a matching result. If True, update the
            matching result in place while preserving its platform ID.

    Returns:
        A RegisteredResult indicating whether the result was created, updated, or skipped.
    """
    validated_entity_uuid = UUID(validated_entity_id)
    existing = _find_existing(client, test_result.name, validated_entity_uuid)

    should_overwrite = overwrite_existing

    if existing is not None:
        existing_id = _result_id(existing)
        if not should_overwrite:
            logger.info(
                "ValidationResult '%s' already exists for entity %s. Skipping.",
                test_result.name,
                validated_entity_id,
            )
            return RegisteredResult(
                entity_id=str(existing_id),
                test_result=test_result,
                skipped=True,
            )

        _update_existing(
            client,
            existing,
            test_result,
            validated_entity_uuid,
            out_dir,
        )
        logger.info(
            "Updated ValidationResult '%s' (id=%s, passed=%s)",
            test_result.name,
            existing_id,
            test_result.passed,
        )
        return RegisteredResult(
            entity_id=str(existing_id),
            test_result=test_result,
            updated=True,
        )

    # Details are persisted as an asset via _upload_details, not as an entity field.
    validation_result = ValidationResult(
        name=test_result.name,
        passed=test_result.passed,
        validated_entity_id=validated_entity_uuid,
    )
    registered = client.register_entity(entity=validation_result)
    entity_id = _result_id(registered)

    _upload_figures(client, entity_id, test_result.figures)
    if out_dir:
        _upload_details(client, entity_id, test_result.name, test_result.details, out_dir)

    logger.info(
        "Registered ValidationResult '%s' (id=%s, passed=%s)",
        test_result.name,
        entity_id,
        test_result.passed,
    )

    return RegisteredResult(entity_id=str(entity_id), test_result=test_result)


def register_outcomes(
    client: Client,
    test_results: list[TestResult],
    validated_entity_id: str,
    *,
    out_dir: Path | None = None,
    overwrite_existing: bool = False,
) -> list[RegisteredResult]:
    """Register multiple test results using one overwrite policy.

    Args:
        client: entitysdk Client instance.
        test_results: List of test results.
        validated_entity_id: The entity ID that was validated.
        out_dir: Directory for writing temporary detail files.
        overwrite_existing: If False, skip matching results. If True, update matching
            results in place while preserving their platform IDs.

    Returns:
        List of RegisteredResult objects.

    Raises:
        ValidationResultAlreadyExistsError: If multiple matching results are found.
    """
    results = []
    for test_result in test_results:
        try:
            result = register_outcome(
                client,
                test_result,
                validated_entity_id,
                out_dir=out_dir,
                overwrite_existing=overwrite_existing,
            )
            results.append(result)
        except ValidationResultAlreadyExistsError:
            # Duplicate matching entities indicate inconsistent persisted state and
            # must not be converted into a generic failed result.
            raise
        except ValidationResultPermissionError as exc:
            # A permission problem is actionable but not a crash: report it clearly
            # for this result and continue with the rest of the batch.
            logger.warning("%s", exc)
            results.append(RegisteredResult(entity_id=None, test_result=test_result))
        except Exception:
            logger.exception(
                "Failed to register ValidationResult '%s' for entity %s",
                test_result.name,
                validated_entity_id,
            )
            results.append(RegisteredResult(entity_id=None, test_result=test_result))
    return results
