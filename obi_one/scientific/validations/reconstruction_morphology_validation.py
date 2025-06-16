import json
import logging
from pathlib import Path
import importlib
from typing import Annotated, ClassVar
from pydantic import BaseModel, Field

from obi_one.core.validation import SingleValidationOutput, Validation

L = logging.getLogger(__name__)

# Define a custom exception for critical validation failures
class CriticalValidationFailedError(Exception):
    """Raised when a 'must_pass_to_upload' validation fails."""
    pass


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

    name: ClassVar[str] = "Reconstruction Morphology Validation"
    description: ClassVar[str] = "Validates the morphology of a reconstruction."
    entity: ClassVar[str] = "cell_morphology" 
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


# Example of another validation class (as defined before)
class AnotherValidationClass:
    name = "Another Validation"
    description = "Checks something else."
    entity="cell_morphology"
    def __init__(self, some_param: str = "default"):
        self.some_param = some_param
        L.info(f"Initialized AnotherValidationClass with param: {self.some_param}")

    def run(self):
        L.info("Running AnotherValidationClass")
        # Simulate an error for demonstration if needed, e.g.:
        # if self.some_param == "error_trigger":
        #    raise ValueError("Simulated error in AnotherValidationClass")
        pass

class YetAnotherValidationClass:
    name = "Another Validation"
    description = "Checks something else."
    entity="cell_morphology"
    def __init__(self, some_param: str = "default"):
        self.some_param = some_param
        L.info(f"Initialized AnotherValidationClass with param: {self.some_param}")

    def run(self):
        L.info("Running YetAnotherValidationClass")
        # Simulate an error for demonstration if needed, e.g.:
        # if self.some_param == "error_trigger":
        #    raise ValueError("Simulated error in AnotherValidationClass")
        pass
    

def run_grouped_categorized_validations_from_config(config_file: Path, module_name: str = "reconstruction_morphology_validation"):
    """
    Reads grouped and categorized validation class names from a JSON configuration file,
    instantiates them, and runs their 'run' method for each entity and category.

    'must_pass_to_upload' validations: If any fail, a CriticalValidationFailedError is raised.
    Other categories: Individual failures are logged but do not stop execution of other validations.

    Args:
        config_file (Path): The path to the JSON configuration file.
        module_name (str): The name of the module where the validation classes are defined.
                           Defaults to 'reconstruction_morphology_validation'.

    Raises:
        CriticalValidationFailedError: If any validation in the 'must_pass_to_upload'
                                       category fails.
    """
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_file}")

    with open(config_file, 'r') as f:
        config = json.load(f)

    all_entities = config.get("entities", {})
    if not all_entities:
        L.warning("No entities specified in the configuration file.")
        return

    # Dynamically import the module containing the validation classes
    try:
        validation_module = importlib.import_module(module_name)
    except ImportError:
        L.error(f"Could not import module: {module_name}. Make sure it's in your PYTHONPATH.")
        return

    for entity_name, categories_data in all_entities.items():
        L.info(f"\n===== Running validations for entity: '{entity_name}' =====")
        if not categories_data:
            L.warning(f"No categories specified for entity '{entity_name}'.")
            continue

        for category, class_names in categories_data.items():
            L.info(f"\n--- Running validations for category: '{category}' under '{entity_name}' ---")
            if not class_names:
                L.info(f"No validations specified for category '{category}' under '{entity_name}'.")
                continue

            for class_name in class_names:
                try:
                    # Get the class object from the dynamically imported module
                    validation_class = getattr(validation_module, class_name)

                    # Check if it's actually a class and has a 'run' method
                    if not isinstance(validation_class, type) or not hasattr(validation_class, 'run'):
                        L.warning(f"  '{class_name}' found in config for category '{category}' under '{entity_name}' "
                                  f"is not a valid validation class or does not have a 'run' method. Skipping.")
                        continue

                    # Instantiate the class
                    if class_name == "ReconstructionMorphologyValidation":
                        # Example: pass a dummy path for ReconstructionMorphologyValidation for demonstration
                        # In a real scenario, this path would come from a more specific config or context
                        instance = validation_class(morphology_file_path=Path("dummy_morphology.swc"))
                    else:
                        instance = validation_class()

                    L.info(f"    Running validation: {instance.name}")
                    instance.run()
                    # If your validation classes have a save method, you might call it here too:
                    # instance.save()

                except AttributeError:
                    L.error(f"    Class '{class_name}' not found in module '{module_name}' for category '{category}' under '{entity_name}'. Skipping.")
                except Exception as e:
                    error_message = f"    Error running validation '{class_name}' in category '{category}' under '{entity_name}': {e}"
                    if category == "must_pass_to_upload":
                        L.critical(error_message) # Log as critical
                        raise CriticalValidationFailedError(f"Critical validation failed: {class_name} in {entity_name}/{category}") from e
                    else:
                        L.error(error_message) # Log as error but continue

# Example Usage:
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO) # Set up basic logging

    # Create a dummy config file for testing
    dummy_config_path = Path("grouped_categorized_config.json")
    config_data = {
        "entities": {
            "entity1": {
                "must_pass_to_upload": ["ReconstructionMorphologyValidation"],
                "must_run_upon_upload": ["AnotherValidationClass"],
                "must_pass_to_simulate": ["YetAnotherValidationClass"]
            },
            "entity2": {
                "must_pass_to_upload": ["AnotherValidationClass"], # If AnotherValidationClass were to raise an error here, it would stop
                "must_run_upon_upload": ["ReconstructionMorphologyValidation", "YetAnotherValidationClass", "NonExistentValidation"],
                "must_pass_to_simulate": []
            }
        }
    }
    with open(dummy_config_path, 'w') as f:
        json.dump(config_data, f, indent=2)

    # Create a dummy morphology file for ReconstructionMorphologyValidation
    dummy_morphology_path = Path("dummy_morphology.swc")
    with open(dummy_morphology_path, 'w') as f:
        f.write("# Dummy SWC content\n1 1 0 0 0 1 1\n") # Minimal valid SWC line

    L.info(f"Running grouped and categorized validations from {dummy_config_path}")
    try:
        run_grouped_categorized_validations_from_config(dummy_config_path)
        L.info("All specified validations completed successfully (or non-critical failures were logged).")
    except CriticalValidationFailedError as e:
        L.error(f"Script terminated due to a critical validation failure: {e}")
    except FileNotFoundError as e:
        L.error(f"Configuration file error: {e}")
    except ImportError as e:
        L.error(f"Module import error: {e}")
    except Exception as e:
        L.error(f"An unexpected error occurred: {e}")
    finally:
        # Clean up dummy files
        dummy_config_path.unlink(missing_ok=True)
        dummy_morphology_path.unlink(missing_ok=True)
