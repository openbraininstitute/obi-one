"""MEModel validation task for task-based execution.

This task wraps the MEModelValidationWorkflow for execution through
the OBI-One task system (launch system / worker infrastructure).
"""

from pathlib import Path

from pydantic import Field

from obi_one.scientific.validations.base import ValidationSingleConfig, ValidationTask
from obi_one.scientific.validations.memodel.workflow import MEModelValidationWorkflow


class MEModelValidationSingleConfig(ValidationSingleConfig):
    """Configuration for MEModel validation task."""

    output_dir: str = Field(
        default="./memodel_validation",
        description="Output directory for MEModel validation artifacts.",
    )
    validation_profile: str = Field(
        default="default",
        description=(
            "Name of the MEModel validation profile to use. Registered profiles "
            "can be selected here; custom profile instances can be passed directly "
            "to MEModelValidationWorkflow."
        ),
    )


class MEModelValidationTask(ValidationTask):
    """Task for running MEModel validation through the OBI-One task system."""

    config: MEModelValidationSingleConfig

    def get_workflow(self) -> MEModelValidationWorkflow:
        return MEModelValidationWorkflow(
            output_dir=Path(self.config.output_dir),
            validation_profile=self.config.validation_profile,
        )
