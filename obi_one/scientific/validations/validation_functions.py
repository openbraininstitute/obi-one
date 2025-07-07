import json
from enum import StrEnum, auto
from typing import Callable, Dict, List, Any, Tuple, Type, TypeVar, Optional
import os
import neurom
import morphio
import logging
L = logging.getLogger(__name__)

# Assume EntityType is defined in an external file, e.g., 'entity_types.py'
# For demonstration, I'll define it here:
class EntityType(StrEnum):
    """Entity types."""
    age = auto()
    analysis_software_source_code = auto()
    emodel = auto()
    experimental_bouton_density = auto()
    experimental_neuron_density = auto()
    experimental_synapses_per_connection = auto()
    memodel = auto()
    mesh = auto()
    cell_morphology = auto()
    electrical_cell_recording = auto()
    electrical_recording_stimulus = auto()
    scientific_artifact = auto()
    single_neuron_simulation = auto()
    single_neuron_synaptome = auto()
    single_neuron_synaptome_simulation = auto()
    subject = auto()
    synaptic_pathway = auto()

# Type alias for a validation function signature: (data, artifact_name) -> (bool, List[str])
# Where 'data' is the entity being validated, and 'artifact_name' is the string.
ValidationResult = Tuple[bool, List[str]]
ValidationFunction = Callable[[Any, str], ValidationResult] # <-- MODIFIED: Added 'str' for artifact_name

# A generic type for the validation objects (e.g., AgeValidations, SubjectValidations)
TValidationObject = TypeVar('TValidationObject')

class ValidationQueue:
    MUST_PASS_TO_UPLOAD = "must-pass-to-upload-list"
    MUST_RUN_UPON_UPLOAD = "must-run-upon-upload-list"
    MUST_PASS_TO_SIMULATE = "must-pass-to-simulate-list"

class EntityValidationManager:
    """
    Manages and runs validations for different entity types across various queues.
    """
    _validation_objects: Dict[EntityType, Any] = {}
    _validation_configs: Dict[str, Dict[str, List[str]]] = {}
    _config_dir: str = ""

    @classmethod
    def set_config_directory(cls, directory_path: str):
        if not os.path.isdir(directory_path):
            raise FileNotFoundError(f"Configuration directory not found: {directory_path}")
        cls._config_dir = directory_path

    @classmethod
    def register_validation_object(cls, entity_type: EntityType, validation_obj: TValidationObject):
        if not hasattr(validation_obj, '_entity_type') or validation_obj._entity_type != entity_type:
            pass
        cls._validation_objects[entity_type] = validation_obj
        if cls._config_dir:
            cls._load_entity_config(entity_type)

    @classmethod
    def _load_entity_config(cls, entity_type: EntityType):
        if not cls._config_dir:
            print(f"Warning: Configuration directory not set. Cannot load config for {entity_type.name}.")
            return

        json_file_name = f"{entity_type.value}.json"
        json_file_path = os.path.join(cls._config_dir, json_file_name)

        try:
            with open(json_file_path, 'r') as f:
                data = json.load(f)
            
            if entity_type.value not in cls._validation_configs:
                cls._validation_configs[entity_type.value] = {}

            for queue_name, func_names in data.items():
                if queue_name not in [ValidationQueue.MUST_PASS_TO_UPLOAD,
                                      ValidationQueue.MUST_RUN_UPON_UPLOAD,
                                      ValidationQueue.MUST_PASS_TO_SIMULATE]:
                    raise ValueError(f"Unknown validation queue '{queue_name}' in {json_file_name}.")
                if not isinstance(func_names, list) or not all(isinstance(f, str) for f in func_names):
                    raise ValueError(f"Invalid function list for '{queue_name}' in {json_file_name}. Must be a list of strings.")
                
                cls._validation_configs[entity_type.value][queue_name] = func_names
            print(f"Loaded validation configurations for {entity_type.name} from {json_file_name}")

        except FileNotFoundError:
            print(f"Warning: No config file found for {entity_type.name} at {json_file_path}. No validations will run for this entity type.")
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from {json_file_path}: {e}")
        except ValueError as e:
            print(f"Error in JSON configuration structure for {json_file_name}: {e}")

    @classmethod
    def _get_validation_func(cls, entity_type: EntityType, func_name: str) -> Optional[ValidationFunction]:
        validation_obj = cls._validation_objects.get(entity_type)
        if not validation_obj:
            print(f"Warning: No validation object registered for EntityType.{entity_type.name}. Cannot find '{func_name}'.")
            return None

        func = getattr(validation_obj, func_name, None)
        if not func or not callable(func):
            print(f"Warning: Validation function '{func_name}' not found or not callable "
                  f"in object for EntityType.{entity_type.name}. Check function name in JSON and class definition.")
            return None
        return func

    @classmethod
    def _get_functions_for_queue(cls, entity_type: EntityType, queue_name: str) -> List[str]:
        entity_config = cls._validation_configs.get(entity_type.value, {})
        return entity_config.get(queue_name, [])

    @classmethod
    def run_must_pass_to_upload(cls, entity_type: EntityType, entity_data: Any, artifact_name: str) -> ValidationResult: # <-- MODIFIED: Added artifact_name
        total_success = True
        all_errors: List[str] = []
        queue_name = ValidationQueue.MUST_PASS_TO_UPLOAD

        functions_to_run = cls._get_functions_for_queue(entity_type, queue_name)

        if not functions_to_run:
            print(f"No '{queue_name}' validations configured for {entity_type.name}.")
            return True, []

        print(f"\n--- Running '{queue_name}' validations for {entity_type.name} (Artifact: '{artifact_name}') ---") # <-- MODIFIED: Added artifact_name to print
        for func_name in functions_to_run:
            validation_func = cls._get_validation_func(entity_type, func_name)
            if validation_func:
                try:
                    success, errors = validation_func(entity_data, artifact_name) # <-- MODIFIED: Pass artifact_name
                    if not success:
                        total_success = False
                        all_errors.extend([f"{func_name}: {err}" for err in errors])
                        print(f"  ❌ {func_name} FAILED: {', '.join(errors)}")
                    else:
                        print(f"  ✅ {func_name} PASSED.")
                except Exception as e:
                    total_success = False
                    error_msg = f"Error executing {func_name}: {e}"
                    all_errors.append(error_msg)
                    print(f"  ❌ {func_name} ERROR: {error_msg}")
            else:
                total_success = False
                error_msg = f"Validation function '{func_name}' not found or invalid for {entity_type.name} (check config and class)."
                all_errors.append(error_msg)

        if total_success:
            print(f"All '{queue_name}' validations PASSED for {entity_type.name}.")
        else:
            print(f"'{queue_name}' validations FAILED for {entity_type.name}.")
        return total_success, all_errors

    @classmethod
    def run_must_run_upon_upload(cls, entity_type: EntityType, entity_data: Any, artifact_name: str) -> ValidationResult: # <-- MODIFIED: Added artifact_name
        total_success = True
        all_errors: List[str] = []
        queue_name = ValidationQueue.MUST_RUN_UPON_UPLOAD

        functions_to_run = cls._get_functions_for_queue(entity_type, queue_name)

        if not functions_to_run:
            print(f"No '{queue_name}' validations configured for {entity_type.name}.")
            return True, []

        print(f"\n--- Running '{queue_name}' validations for {entity_type.name} (Artifact: '{artifact_name}') ---") # <-- MODIFIED: Added artifact_name to print
        for func_name in functions_to_run:
            validation_func = cls._get_validation_func(entity_type, func_name)
            if validation_func:
                try:
                    success, errors = validation_func(entity_data, artifact_name) # <-- MODIFIED: Pass artifact_name
                    if not success:
                        all_errors.extend([f"{func_name}: {err}" for err in errors])
                        total_success = False
                        print(f"  ⚠️ {func_name} reported internal issue: {', '.join(errors)}")
                    else:
                        print(f"  ⚙️ {func_name} RAN (reported success).")
                except Exception as e:
                    total_success = False
                    error_msg = f"Error executing {func_name}: {e}"
                    all_errors.append(error_msg)
                    print(f"  ❌ {func_name} ERROR: {error_msg}")
            else:
                total_success = False
                error_msg = f"Validation function '{func_name}' not found or invalid for {entity_type.name} (check config and class)."
                all_errors.append(error_msg)

        if total_success:
            print(f"All '{queue_name}' actions completed for {entity_type.name}.")
        else:
            print(f"'{queue_name}' actions completed with issues for {entity_type.name}.")
        return total_success, all_errors


    @classmethod
    def run_must_pass_to_simulate(cls, entity_type: EntityType, entity_data: Any, artifact_name: str) -> ValidationResult: # <-- MODIFIED: Added artifact_name
        total_success = True
        all_errors: List[str] = []
        queue_name = ValidationQueue.MUST_PASS_TO_SIMULATE

        functions_to_run = cls._get_functions_for_queue(entity_type, queue_name)

        if not functions_to_run:
            print(f"No '{queue_name}' validations configured for {entity_type.name}.")
            return True, []

        print(f"\n--- Running '{queue_name}' validations for {entity_type.name} (Artifact: '{artifact_name}') ---") # <-- MODIFIED: Added artifact_name to print
        for func_name in functions_to_run:
            validation_func = cls._get_validation_func(entity_type, func_name)
            if validation_func:
                try:
                    success, errors = validation_func(entity_data, artifact_name) # <-- MODIFIED: Pass artifact_name
                    if not success:
                        total_success = False
                        all_errors.extend([f"{func_name}: {err}" for err in errors])
                        print(f"  ❌ {func_name} FAILED: {', '.join(errors)}")
                    else:
                        print(f"  ✅ {func_name} PASSED.")
                except Exception as e:
                    total_success = False
                    error_msg = f"Error executing {func_name}: {e}"
                    all_errors.append(error_msg)
                    print(f"  ❌ {func_name} ERROR: {error_msg}")
            else:
                total_success = False
                error_msg = f"Validation function '{func_name}' not found or invalid for {entity_type.name} (check config and class)."
                all_errors.append(error_msg)

        if total_success:
            print(f"All '{queue_name}' validations PASSED for {entity_type.name}.")
        else:
            print(f"'{queue_name}' validations FAILED for {entity_type.name}.")
        return total_success, all_errors

# --- Define Validation Objects (MODIFIED to accept artifact_name) ---

class MorphologyValidations:
    """Validation functions for the 'cell_morphology' entity type."""
    _entity_type = EntityType.cell_morphology

    def is_loadable(self, value: Any, artifact_name: str) -> ValidationResult: # <-- MODIFIED
        morphology_file_path=str(value);
        L.info("Running Reconstruction Morphology Validation")

        if not morphology_file_path:
            return False, ["File path must be provided for validation."]
        try:
            #neurom_morphology = neurom.load_morphology(morphology_file_path)
            morphio_morphology = morphio.Morphology(morphology_file_path)
        except:
            return False, ["Not loadable"]

        return True, []

'''
# --- Setup and Example Usage (MODIFIED to include artifact_name) ---

# 1. Create a directory for validation configs
CONFIG_DIR = "validation_configs"
os.makedirs(CONFIG_DIR, exist_ok=True)
print(f"Ensured configuration directory exists: {CONFIG_DIR}")

# 2. Create entity-specific JSON files (same as before, no change here)
# cell_morphology.json
cell_morphology_config_data = {
    ValidationQueue.MUST_PASS_TO_UPLOAD: [
        "is_loadable",
       
    ]
}
with open(os.path.join(CONFIG_DIR, f"{EntityType.cell_morphology.value}.json"), "w") as f:
    json.dump(cell_morphology_config_data, f, indent=4)
print(f"Created {EntityType.cell_morphology.value}.json")


# 3. Set the configuration directory
EntityValidationManager.set_config_directory(CONFIG_DIR)

# 4. Register validation objects for each entity type.
EntityValidationManager.register_validation_object(EntityType.cell_morphology, MorphologyValidations())

if __name__ == "__main__":
    print("\n--- Running morphology Validations ---")
    
    # Define an artifact name for these tests
    current_artifact_name = "data_upload_2025_07_04_cell_morphology"

    # Valid morphology
    morphology_asset_1 = "/home/dkeller/simple.swc"
    success, errors = EntityValidationManager.run_must_pass_to_upload(EntityType.cell_morphology, morphology_asset_1, current_artifact_name) # <-- MODIFIED
    print(f"Overall morphology validation success: {success}, Errors: {errors}")

'''
