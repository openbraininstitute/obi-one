# validation_functions.py
import json
from enum import StrEnum, auto
from typing import Callable, Dict, List, Any, Tuple, Type, TypeVar, Optional
import os
import neurom
import morphio
import logging
import inspect

L = logging.getLogger(__name__)

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

ValidationResult = Tuple[bool, List[str]]
ValidationFunction = Callable[[Any, str], ValidationResult]

TValidationObject = TypeVar('TValidationObject')

class BaseValidations:
    _entity_type: EntityType = None

    def get_available_validations(self) -> List[str]:
        """
        Returns a list of public method names (validation functions)
        available in this validation class, excluding itself.
        """
        validation_functions = []
        # Methods to explicitly exclude from the list of selectable validations
        EXCLUDED_METHODS = ['get_available_validations'] # Add other helper methods if they appear

        for name, member in inspect.getmembers(self, predicate=inspect.ismethod):
            # Exclude private methods, dunder methods, and explicitly excluded methods
            if not name.startswith('_') and not name.startswith('__') and name not in EXCLUDED_METHODS and callable(member):
                validation_functions.append(name)
        return validation_functions

class ValidationQueue:
    MUST_PASS_TO_UPLOAD = "must_pass_to_upload"
    MUST_RUN_UPON_UPLOAD = "must_run_upon_upload"
    MUST_PASS_TO_SIMULATE = "must_pass_to_simulate"

class EntityValidationManager:
    _validation_objects: Dict[EntityType, BaseValidations] = {}
    _validation_configs: Dict[str, Dict[str, List[str]]] = {}
    _config_directory: Optional[str] = None

    @classmethod
    def set_config_directory(cls, path: str):
        cls._config_directory = path

    @classmethod
    def register_validation_object(cls, entity_type: EntityType, validation_object: BaseValidations):
        if not isinstance(validation_object, BaseValidations):
            raise TypeError("Validation object must inherit from BaseValidations")
        if validation_object._entity_type != entity_type:
            raise ValueError(f"Validation object entity type mismatch. Expected {entity_type.value}, got {validation_object._entity_type.value}")
        cls._validation_objects[entity_type] = validation_object
        L.info(f"Registered validation object for {entity_type.value}")

    @classmethod
    def _load_entity_config(cls, entity_type: EntityType):
        if not cls._config_directory:
            L.warning(f"Configuration directory not set. Cannot load config for {entity_type.name}.")
            return

        json_file_name = f"{entity_type.value}.json"
        json_file_path = os.path.join(cls._config_directory, json_file_name)

        try:
            with open(json_file_path, 'r') as f:
                data = json.load(f)

            if entity_type.value not in cls._validation_configs:
                cls._validation_configs[entity_type.value] = {}

            valid_queue_names = [
                ValidationQueue.MUST_PASS_TO_UPLOAD,
                ValidationQueue.MUST_RUN_UPON_UPLOAD,
                ValidationQueue.MUST_PASS_TO_SIMULATE
            ]

            for queue_name, func_names in data.items():
                if queue_name not in valid_queue_names:
                    raise ValueError(f"Unknown validation queue '{queue_name}' in {json_file_name}.")
                if not isinstance(func_names, list) or not all(isinstance(f, str) for f in func_names):
                    raise ValueError(f"Invalid function list for '{queue_name}' in {json_file_name}. Must be a list of strings.")

                cls._validation_configs[entity_type.value][queue_name] = func_names
            L.info(f"Loaded validation configurations for {entity_type.name} from {json_file_name}")

        except FileNotFoundError:
            L.warning(f"No config file found for {entity_type.name} at {json_file_path}.")
        except json.JSONDecodeError as e:
            L.error(f"Error decoding JSON from {json_file_path}: {e}")
        except ValueError as e:
            L.error(f"Error in JSON configuration structure for {json_file_name}: {e}")

    @classmethod
    def _get_validation_func(cls, entity_type: EntityType, func_name: str) -> Optional[ValidationFunction]:
        validation_obj = cls._validation_objects.get(entity_type)
        if not validation_obj:
            L.warning(f"No validation object registered for EntityType.{entity_type.name}. Cannot find '{func_name}'.")
            return None

        func = getattr(validation_obj, func_name, None)
        if not func or not callable(func):
            L.warning(f"Validation function '{func_name}' not found or not callable "
                      f"in object for EntityType.{entity_type.name}. Check function name in JSON and class definition.")
            return None
        return func

    @classmethod
    def _get_functions_for_queue(cls, entity_type: EntityType, queue_name: str) -> List[str]:
        if entity_type.value not in cls._validation_configs and cls._config_directory:
            cls._load_entity_config(entity_type)
        entity_config = cls._validation_configs.get(entity_type.value, {})
        return entity_config.get(queue_name, [])

    @classmethod
    def run_must_pass_to_upload(cls, entity_type: EntityType, entity_data: Any, artifact_name: str) -> ValidationResult:
        total_success = True
        all_errors: List[str] = []
        queue_name = ValidationQueue.MUST_PASS_TO_UPLOAD

        functions_to_run = cls._get_functions_for_queue(entity_type, queue_name)

        if not functions_to_run:
            L.info(f"No '{queue_name}' validations configured for {entity_type.name}.")
            return True, []

        L.info(f"\n--- Running '{queue_name}' validations for {entity_type.name} (Artifact: '{artifact_name}') ---")
        for func_name in functions_to_run:
            validation_func = cls._get_validation_func(entity_type, func_name)
            if validation_func:
                try:
                    success, errors = validation_func(entity_data, artifact_name)
                    if not success:
                        total_success = False
                        all_errors.extend([f"{func_name}: {err}" for err in errors])
                        L.info(f"  ❌ {func_name} FAILED: {', '.join(errors)}")
                    else:
                        L.info(f"  ✅ {func_name} PASSED.")
                except Exception as e:
                    total_success = False
                    error_msg = f"Error executing {func_name}: {e}"
                    all_errors.append(error_msg)
                    L.error(f"  ❌ {func_name} ERROR: {error_msg}")
            else:
                total_success = False
                error_msg = f"Validation function '{func_name}' not found or invalid for {entity_type.name} (check config and class)."
                all_errors.append(error_msg)

        if total_success:
            L.info(f"All '{queue_name}' validations PASSED for {entity_type.name}.")
        else:
            L.warning(f"'{queue_name}' validations FAILED for {entity_type.name}.")
        return total_success, all_errors

    @classmethod
    def run_must_run_upon_upload(cls, entity_type: EntityType, entity_data: Any, artifact_name: str) -> ValidationResult:
        total_success = True
        all_errors: List[str] = []
        queue_name = ValidationQueue.MUST_RUN_UPON_UPLOAD

        functions_to_run = cls._get_functions_for_queue(entity_type, queue_name)

        if not functions_to_run:
            L.info(f"No '{queue_name}' validations configured for {entity_type.name}.")
            return True, []

        L.info(f"\n--- Running '{queue_name}' validations for {entity_type.name} (Artifact: '{artifact_name}') ---")
        for func_name in functions_to_run:
            validation_func = cls._get_validation_func(entity_type, func_name)
            if validation_func:
                try:
                    success, errors = validation_func(entity_data, artifact_name)
                    if not success:
                        all_errors.extend([f"{func_name}: {err}" for err in errors])
                        total_success = False # Still consider it a failure for overall summary if issues arise
                        L.warning(f"  ⚠️ {func_name} reported internal issue: {', '.join(errors)}")
                    else:
                        L.info(f"  ⚙️ {func_name} RAN (reported success).")
                except Exception as e:
                    total_success = False
                    error_msg = f"Error executing {func_name}: {e}"
                    all_errors.append(error_msg)
                    L.error(f"  ❌ {func_name} ERROR: {error_msg}")
            else:
                total_success = False
                error_msg = f"Validation function '{func_name}' not found or invalid for {entity_type.name} (check config and class)."
                all_errors.append(error_msg)

        if total_success:
            L.info(f"All '{queue_name}' actions completed for {entity_type.name}.")
        else:
            L.warning(f"'{queue_name}' actions completed with issues for {entity_type.name}.")
        return total_success, all_errors


    @classmethod
    def run_must_pass_to_simulate(cls, entity_type: EntityType, entity_data: Any, artifact_name: str) -> ValidationResult:
        total_success = True
        all_errors: List[str] = []
        queue_name = ValidationQueue.MUST_PASS_TO_SIMULATE

        functions_to_run = cls._get_functions_for_queue(entity_type, queue_name)

        if not functions_to_run:
            L.info(f"No '{queue_name}' validations configured for {entity_type.name}.")
            return True, []

        L.info(f"\n--- Running '{queue_name}' validations for {entity_type.name} (Artifact: '{artifact_name}') ---")
        for func_name in functions_to_run:
            validation_func = cls._get_validation_func(entity_type, func_name)
            if validation_func:
                try:
                    success, errors = validation_func(entity_data, artifact_name)
                    if not success:
                        total_success = False
                        all_errors.extend([f"{func_name}: {err}" for err in errors])
                        L.info(f"  ❌ {func_name} FAILED: {', '.join(errors)}")
                    else:
                        L.info(f"  ✅ {func_name} PASSED.")
                except Exception as e:
                    total_success = False
                    error_msg = f"Error executing {func_name}: {e}"
                    all_errors.append(error_msg)
                    L.error(f"  ❌ {func_name} ERROR: {error_msg}")
            else:
                total_success = False
                error_msg = f"Validation function '{func_name}' not found or invalid for {entity_type.name} (check config and class)."
                all_errors.append(error_msg)

        if total_success:
            L.info(f"All '{queue_name}' validations PASSED for {entity_type.name}.")
        else:
            L.warning(f"'{queue_name}' validations FAILED for {entity_type.name}.")
        return total_success, all_errors

class MorphologyValidations(BaseValidations):
    """Validation functions for the 'cell_morphology' entity type."""
    _entity_type = EntityType.cell_morphology

    def is_loadable(self, value: Any, artifact_name: str) -> ValidationResult:
        morphology_file_path=str(value);
        L.info(f"Running Reconstruction Morphology Validation (is_loadable) for artifact: {artifact_name}")

        if not morphology_file_path:
            return False, ["File path must be provided for validation."]
        try:
            morphio.Morphology(morphology_file_path)
            return True, []
        except Exception as e:
            L.error(f"Morphology {morphology_file_path} (artifact: {artifact_name}) failed to load: {e}")
            return False, [f"Morphology failed to load: {e}"]

    def has_soma(self, morphology_path: str, artifact_name: str) -> ValidationResult:
        """
        Checks if the morphology has a soma.
        """
        L.info(f"Running Morphology Validation (has_soma) for artifact: {artifact_name}")
        try:
            m = morphio.Morphology(morphology_path)
            if not m.soma:
                return False, ["Morphology has no soma."]
            return True, []
        except Exception as e:
            L.error(f"Error checking soma for {morphology_path} (artifact: {artifact_name}): {e}")
            return False, [f"Error checking soma: {e}"]
