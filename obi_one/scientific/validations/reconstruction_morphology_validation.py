from obi_one.scientific.validations.validation import Validation

import neurom
import morphio

from typing import ClassVar, Annotated

from pydantic import BaseModel, Field

from pathlib import Path

import logging

L = logging.getLogger(__name__)

class ReconstructionMorphologyValidationOutput(BaseModel):
    validation_a: Annotated[
        bool,
        Field(
            title="validation_a",
            description="description of validation_a",
        ),
    ]
    validation_b: Annotated[
        bool,
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
            validation_a=True,
            validation_b=False,
        )

        # Implement the validation logic here
        pass

    def save(self) -> None:
        """Save the result of the validation."""
        
        L.info("Saving Reconstruction Morphology Validation Output")

        if self._validation_output is None:
            raise ValueError("Validation output must be set before saving.")
        
        # Example: Save the validation output to a database or file

        pass

