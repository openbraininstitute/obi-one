"""Entity-agnostic validation workflow base class."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bluecellulab.validation.base import ValidationOutcome, ValidationTest


@dataclass
class WorkflowContext:
    """Context produced by workflow setup, consumed by test execution.

    This is intentionally generic — each entity-specific workflow subclass
    populates it with whatever its tests need.

    Attributes:
        entity_id: The platform entity ID being validated.
        template_params: Cell template parameters (for electrophys workflows).
        rheobase: Computed or stored rheobase current.
        out_dir: Output directory for figures and artifacts.
        extra: Additional context specific to the entity type.
    """

    entity_id: str
    template_params: Any = None
    rheobase: float | None = None
    out_dir: Path | None = None
    extra: dict = field(default_factory=dict)


class ValidationWorkflow(ABC):
    """Abstract base for entity validation workflows.

    A workflow encapsulates the full lifecycle:
    1. setup — download/prepare the entity
    2. get_tests — return the list of ValidationTests to run
    3. run — execute all tests and collect outcomes
    4. register — persist outcomes as ValidationResult entities

    The workflow is independent of the execution backend. It can be called
    from a notebook, an OBI-One Task, or any other orchestrator.
    """

    @abstractmethod
    def setup(self, entity_id: str, client) -> WorkflowContext:
        """Download and prepare the entity for validation.

        Args:
            entity_id: Platform entity ID.
            client: entitysdk Client instance.

        Returns:
            A WorkflowContext with everything tests need to run.
        """

    @abstractmethod
    def get_tests(self, context: WorkflowContext) -> list[ValidationTest]:
        """Return the validation tests to execute.

        Args:
            context: The workflow context from setup().

        Returns:
            List of ValidationTest instances configured for this entity.
        """

    def run(self, context: WorkflowContext) -> list[ValidationOutcome]:
        """Execute all tests and collect outcomes.

        Args:
            context: The workflow context from setup().

        Returns:
            List of ValidationOutcome results.
        """
        tests = self.get_tests(context)
        outcomes = []
        for test in tests:
            outcome = test.run(
                context.template_params,
                context.rheobase,
                context.out_dir,
            )
            outcomes.append(outcome)
        return outcomes
