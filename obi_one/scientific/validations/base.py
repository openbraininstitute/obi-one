"""Entity-agnostic validation workflow and task base classes."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from bluecellulab.validation.base import TestResult, ValidationTest
from entitysdk import Client
from pydantic import Field

from obi_one.core.base import OBIBaseModel
from obi_one.core.task import Task

logger = logging.getLogger(__name__)


class InvalidValidationContextError(ValueError):
    """Raised when a workflow context lacks required test inputs."""


@dataclass
class WorkflowContext:
    """Context produced by workflow setup, consumed by test execution.

    This is intentionally generic — each entity-specific workflow subclass
    populates it with whatever its tests need via subclassing or the extra dict.

    Attributes:
        entity_id: The platform entity ID being validated.
        extra: Additional context specific to the entity type.
    """

    entity_id: str
    extra: dict = field(default_factory=dict)


class ValidationWorkflow[ContextT: WorkflowContext](ABC):
    """Abstract base for entity validation workflows.

    A workflow encapsulates the full lifecycle:
    1. setup — download/prepare the entity
    2. get_tests — return the list of ValidationTests to run
    3. run — execute all tests and collect test results
    4. register — persist test results as ValidationResult entities

    The workflow is independent of the execution backend. It can be called
    from a notebook, an OBI-One Task, or any other orchestrator.
    """

    @abstractmethod
    def setup(self, entity_id: str, client: Client) -> ContextT:
        """Download and prepare the entity for validation.

        Args:
            entity_id: Platform entity ID.
            client: entitysdk Client instance.

        Returns:
            A WorkflowContext with everything tests need to run.
        """

    @abstractmethod
    def get_tests(self, context: ContextT) -> list[ValidationTest]:
        """Return the validation tests to execute.

        Args:
            context: The workflow context from setup().

        Returns:
            List of ValidationTest instances configured for this entity.
        """

    @abstractmethod
    def register(
        self,
        test_results: list[TestResult],
        context: ContextT,
        client: Client,
        *,
        skip_if_exists: bool = True,
    ) -> list[Any]:
        """Register test results on the platform.

        Args:
            test_results: Results produced by run().
            context: The workflow context from setup().
            client: entitysdk Client instance.
            skip_if_exists: Whether to skip already registered results.

        Returns:
            Registered result records produced by the entity-specific workflow.
        """

    @abstractmethod
    def run(self, context: ContextT) -> list[TestResult]:
        """Execute the configured validations.

        Args:
            context: The workflow context from setup().

        Returns:
            List of TestResult results.
        """


class ValidationSingleConfig(OBIBaseModel):
    """Base configuration for any validation task execution.

    Attributes:
        entity_id: The entity ID to validate.
        output_dir: Directory for validation output (figures, artifacts).
        skip_if_exists: Skip registration if ValidationResult already exists.
    """

    entity_id: str = Field(description="Entity ID to validate.")
    output_dir: str = Field(
        default="./validation_output",
        description="Output directory for validation artifacts.",
    )
    skip_if_exists: bool = Field(
        default=True,
        description="Skip registration if a ValidationResult already exists for this entity.",
    )


class ValidationTask(Task):
    """Entity-agnostic validation task.

    Subclasses only need to implement get_workflow() to return the appropriate
    ValidationWorkflow for their entity type.

    This task:
    1. Sets up the entity via the workflow
    2. Runs all configured validations
    3. Registers ValidationResult entities on the platform
    4. Updates the execution activity with generated IDs
    """

    config: ValidationSingleConfig

    def get_workflow(self) -> ValidationWorkflow[Any]:
        """Return the ValidationWorkflow instance for this task.

        Subclasses override this to provide entity-specific workflows.
        """
        msg = "Subclasses must implement get_workflow()"
        raise NotImplementedError(msg)

    def execute(
        self,
        *,
        db_client: Client = None,  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,
        execution_activity_id: str | None = None,
    ) -> list[str]:
        """Execute the validation workflow.

        Args:
            db_client: entitysdk Client for platform interaction.
            entity_cache: Whether to use entity caching (unused here).
            execution_activity_id: Optional execution activity to update.

        Returns:
            List of registered ValidationResult entity IDs.
        """
        _ = entity_cache  # intentionally unused

        execution_activity = self._get_execution_activity(
            db_client=db_client,
            execution_activity_id=execution_activity_id,
        )

        workflow = self.get_workflow()

        logger.info("Starting validation for entity %s", self.config.entity_id)

        context = workflow.setup(
            entity_id=self.config.entity_id,
            client=db_client,
        )

        test_results = workflow.run(context)

        registered = workflow.register(
            test_results=test_results,
            context=context,
            client=db_client,
            skip_if_exists=self.config.skip_if_exists,
        )

        generated_ids = [r.entity_id for r in registered if r.entity_id]

        logger.info(
            "Validation complete. Registered %d ValidationResult(s) for entity %s",
            len(generated_ids),
            self.config.entity_id,
        )

        self._update_execution_activity(
            db_client=db_client,
            execution_activity=execution_activity,
            generated=generated_ids,
        )

        return generated_ids
