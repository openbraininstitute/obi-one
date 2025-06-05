from obi_one.scientific.validations.validation import Validation

class ReconstructionMorphologyValidation(Validation):
    """Validate the morphology of a reconstruction.

    This validation checks if the morphology of a reconstruction is valid.
    It is used to ensure that the morphology data meets certain criteria.
    """

    name: str = "Validate Reconstruction Morphology"
    description: str | None = "Validates the morphology of a reconstruction."

    def run(self) -> None:
        """Run the validation logic."""
        # Implement the validation logic here
        pass

    def save(self) -> None:
        """Save the result of the validation."""
        # Implement the save logic here using entitysdk
        pass

