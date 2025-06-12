import logging
from pathlib import Path
from typing import Annotated, ClassVar

import morphio
import neurom
from pydantic import BaseModel, Field

from obi_one.core.validation import SingleValidationOutput, Validation

L = logging.getLogger(__name__)


class SingleReconstructionMorphologyValidationOutput(SingleValidationOutput):
    """Single output for a reconstruction morphology validation."""


class ReconstructionMorphologyValidationOutput(Validation):
    validation_a: Annotated[
        SingleReconstructionMorphologyValidationOutput,
        Field(
            title="validation_a",
            description="description of validation_a",
        ),
    ]
    validation_b: Annotated[
        SingleReconstructionMorphologyValidationOutput,
        Field(
            title="validation_b",
            description="description of validation_b",
        ),
    ]


class ReconstructionMorphologyValidation(Validation):
    """Validate the morphology of a reconstruction.

    This validation checks if the morphology of a reconstruction is valid.
    It is used to ensure that the morphology data meets certain criteria.
    """

    name: ClassVar[str] = "Validate Reconstruction Morphology"
    description: ClassVar[str] = "Validates the morphology of a reconstruction."
    morphology_file_path: Path | None = None

    _validation_output: ReconstructionMorphologyValidationOutput | None = None

    def run(self) -> None:
        """Run the validation logic."""
        L.info("Running Reconstruction Morphology Validation")

        if not self.morphology_file_path:
            raise ValueError("File path must be provided for validation.")

        neurom_morphology = neurom.load_morphology(self.morphology_file_path)
        morphio_morphology = morphio.Morphology(self.morphology_file_path)

        self._validation_output = ReconstructionMorphologyValidationOutput(
            validation_a=SingleReconstructionMorphologyValidationOutput(
                name="Morphology Validation A",
                passed=True,
                validation_details="Morphology is valid.",
            ),
            validation_b=SingleReconstructionMorphologyValidationOutput(
                name="Morphology Validation B",
                passed=False,
                validation_details="Axon section is missing.",
            ),
        )

        # Implement the validation logic here

    def save(self) -> None:
        """Save the result of the validation."""
        L.info("Saving Reconstruction Morphology Validation Output")

        if self._validation_output is None:
            raise ValueError("Validation output must be set before saving.")

        # Example: Save the validation output to a database or file
