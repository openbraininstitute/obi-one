"""MEModel validation workflow.

Orchestrates the full validation lifecycle for an MEModel entity:
1. Download the model (HOC, morphology, mechanisms)
2. Compile mechanisms and create a BlueCelluLab Cell
3. Compute electrophysiology properties (rheobase, Rin)
4. Run configured validation tests
5. (Optionally) register results on the platform

This workflow is independent of the execution backend.
"""

import logging
import math
import subprocess  # ruff: ignore[suspicious-subprocess-import]
from contextlib import chdir
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import neuron
from bluecellulab.validation.base import TestResult, ValidationTest
from entitysdk import Client
from entitysdk.downloaders.memodel import download_memodel
from entitysdk.models import MEModel
from entitysdk.schemas.memodel import DownloadedMEModel
from entitysdk.types import EntityLifecycleStatus

from obi_one.db_sdk.db_sdk import update_entity_lifecycle_status
from obi_one.scientific.validations.base import (
    InvalidValidationContextError,
    ValidationWorkflow,
    WorkflowContext,
)
from obi_one.scientific.validations.memodel.config import (
    SimulatorConfig,
    extract_simulator_config_from_hoc,
)
from obi_one.scientific.validations.memodel.profiles import (
    MEModelValidationProfile,
    get_validation_profile,
)
from obi_one.scientific.validations.registration import register_outcomes

logger = logging.getLogger(__name__)


def _compile_mechanisms(mechanisms_dir: Path, output_dir: Path) -> None:
    """Compile model mechanisms and fail before Cell construction on errors."""
    logger.info("Compiling mechanisms from: %s", mechanisms_dir)
    try:
        subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            ["nrnivmodl", str(mechanisms_dir)],  # ruff: ignore[start-process-with-partial-path]
            capture_output=True,
            text=True,
            cwd=str(output_dir),
            check=True,
        )
    except FileNotFoundError as error:
        message = f"Could not find nrnivmodl while compiling mechanisms in {mechanisms_dir}."
        raise InvalidValidationContextError(message) from error
    except subprocess.CalledProcessError as error:
        message = (
            f"nrnivmodl failed with exit code {error.returncode} for mechanisms in "
            f"{mechanisms_dir} (build directory: {output_dir}).\n"
            f"stdout:\n{error.stdout or ''}\n"
            f"stderr:\n{error.stderr or ''}"
        )
        raise InvalidValidationContextError(message) from error


def _load_compiled_mechanisms(output_dir: Path) -> Path:
    """Load the compiled NEURON library for the current platform."""
    candidate_directories = (
        output_dir / "arm64",
        output_dir / "x86_64" / ".libs",
        output_dir / "x86_64",
    )
    candidates = [
        library
        for directory in candidate_directories
        for library in directory.glob("libnrnmech.*")
        if library.is_file()
    ]
    if not candidates:
        message = (
            "nrnivmodl completed but produced no libnrnmech library under "
            f"{output_dir}. Checked: {', '.join(str(path) for path in candidate_directories)}."
        )
        raise InvalidValidationContextError(message)

    load_errors: list[str] = []
    for library in candidates:
        try:
            neuron.h.nrn_load_dll(str(library))
        except (OSError, RuntimeError) as error:
            load_errors.append(f"{library}: {error}")
            continue
        logger.info("Loaded compiled mechanisms from: %s", library)
        return library

    message = (
        f"Could not load compiled NEURON mechanisms from {output_dir}. "
        f"Tried: {', '.join(str(path) for path in candidates)}."
    )
    if load_errors:
        message += f" Loader errors: {' | '.join(load_errors)}"
    raise InvalidValidationContextError(message)


def _resolve_holding_current(
    calibration: Any,
    validation_profile: MEModelValidationProfile,
) -> float:
    """Resolve the calibrated holding current without inventing model values.

    When the calibration carries no ``holding_current``, the result is 0.0 nA
    (no holding), which is the correct default for profiles whose protocols set
    their own holding (e.g. the thalamic tonic-firing hold or the fixed rebound
    holding). A profile that genuinely needs a nonzero calibrated holding opts
    in by overriding ``requires_holding_current``; only then does a missing
    value raise instead of defaulting to 0.0.
    """
    holding_current = getattr(calibration, "holding_current", None)
    if holding_current is None:
        if validation_profile.requires_holding_current:
            message = (
                f"Validation profile '{validation_profile.profile_name}' requires "
                "calibration_result.holding_current."
            )
            raise InvalidValidationContextError(message)
        return 0.0

    try:
        resolved_holding_current = float(holding_current)
    except (TypeError, ValueError) as error:
        message = (
            f"Calibration result holding_current must be a finite number; got {holding_current!r}."
        )
        raise InvalidValidationContextError(message) from error
    if not math.isfinite(resolved_holding_current):
        message = (
            f"Calibration result holding_current must be a finite number; got {holding_current!r}."
        )
        raise InvalidValidationContextError(message)
    return resolved_holding_current


def _select_morphology_path(downloaded: DownloadedMEModel, entity_id: str) -> Path:
    """Return the morphology path a Cell is built from.

    ``download_memodel`` stages every morphology format the entity carries
    (asc, swc, h5, ...) in ``morphology_paths``. The v6 HOC loads .asc or .swc,
    so prefer .asc and fall back to .swc rather than taking an arbitrary entry.
    """
    if not downloaded.morphology_paths:
        message = f"No morphology was downloaded for MEModel {entity_id}."
        raise InvalidValidationContextError(message)
    by_suffix = {path.suffix.lower(): path for path in downloaded.morphology_paths}
    for suffix in (".asc", ".swc"):
        if suffix in by_suffix:
            return by_suffix[suffix]
    message = (
        f"No .asc or .swc morphology was downloaded for MEModel {entity_id}; "
        f"got {[p.name for p in downloaded.morphology_paths]}."
    )
    raise InvalidValidationContextError(message)


def _resolve_rheobase(
    validation_profile: MEModelValidationProfile,
    cell: Any,
    threshold_current: float | None,
) -> float:
    """Return the rheobase for a profile, recomputing it when required.

    Profiles that run percentage-scaled step protocols recompute rheobase at the
    HOC conditions, because the registered calibration may carry a placeholder
    or a wrong-temperature value that breaks rheobase-scaled sweeps. Otherwise
    the calibration ``threshold_current`` is reused when present.
    """
    from bluecellulab.tools import (  # ruff: ignore[import-outside-top-level]
        calculate_rheobase,
    )

    if not (validation_profile.recompute_rheobase or not threshold_current):
        return threshold_current
    rheobase = calculate_rheobase(cell=cell, section="soma[0]", segx=0.5, threshold_voltage=-40.0)
    if validation_profile.recompute_rheobase and threshold_current:
        logger.info(
            "Recomputed rheobase=%.4f nA at HOC conditions (calibration "
            "threshold_current=%.4f nA ignored for this profile).",
            rheobase,
            threshold_current,
        )
    return rheobase


def _verify_simulator_configuration(simulator_config: SimulatorConfig) -> None:
    """Verify global NEURON state and the loaded HOC contract."""
    actual_celsius = float(neuron.h.celsius)
    actual_v_init = float(neuron.h.v_init)
    if not math.isclose(actual_celsius, simulator_config.celsius, abs_tol=1e-9) or not math.isclose(
        actual_v_init, simulator_config.v_init, abs_tol=1e-9
    ):
        message = (
            "Applied NEURON simulator configuration does not match the loaded model "
            f"contract: expected celsius={simulator_config.celsius}, "
            f"v_init={simulator_config.v_init}; got celsius={actual_celsius}, "
            f"v_init={actual_v_init}."
        )
        raise InvalidValidationContextError(message)

    check_simulator = getattr(neuron.h, "check_simulator", None)
    if check_simulator is None:
        logger.warning(
            "Loaded HOC template does not expose check_simulator(); "
            "runtime HOC configuration could not be independently verified."
        )
        return

    try:
        check_simulator()
    except Exception as error:
        message = (
            "Loaded HOC check_simulator() rejected the applied validation "
            f"configuration celsius={actual_celsius}, v_init={actual_v_init}."
        )
        raise InvalidValidationContextError(message) from error


@dataclass
class MEModelWorkflowContext(WorkflowContext):
    """Workflow context for MEModel parametric validation.

    Extends the generic WorkflowContext with electrophysiology-specific fields
    required by BlueCelluLab parametric tests.

    Attributes:
        template_params: BlueCelluLab TemplateParams for creating the cell.
        rheobase: The rheobase (threshold) current in nA.
        rin: The input resistance in MOhm, when required by a profile.
        out_dir: Output directory for figures and artifacts.
        simulator_config: Global NEURON conditions applied for this run.

    Pre-held profiles apply the cell's calibrated holding current via
    ``add_hypamp`` (from ``template_params.emodel_properties.holding_current``),
    so the hold is not carried as a separate context field.
    """

    template_params: Any = None
    rheobase: float | None = None
    rin: float | None = None
    out_dir: Path | None = None
    simulator_config: SimulatorConfig | None = None


class MEModelValidationWorkflow(ValidationWorkflow[MEModelWorkflowContext]):
    """Validation workflow for MEModel (SimulatableNeuron) entities.

    Attributes:
        output_dir: Base directory for validation output (figures, details).
        custom_tests: Additional tests to run beyond the selected profile.
        validation_profile: Policy that provides context requirements and tests.
    """

    def __init__(
        self,
        output_dir: str | Path = "./memodel_validation_output",
        custom_tests: list[ValidationTest] | None = None,
        *,
        validation_profile: str | MEModelValidationProfile | None = None,
    ) -> None:
        """Initialize the MEModel validation workflow.

        Args:
            output_dir: Base directory for validation output.
            custom_tests: Additional tests to run beyond the selected profile.
            validation_profile: A registered profile name or a custom profile
                instance. The default profile is used when omitted.
        """
        self.output_dir = Path(output_dir).resolve()
        self.custom_tests = custom_tests or []
        self.validation_profile = get_validation_profile(validation_profile)

    def setup(self, entity_id: str, client: Client) -> MEModelWorkflowContext:
        """Download and prepare the MEModel and compute required properties.

        Args:
            entity_id: MEModel entity ID on the platform.
            client: entitysdk Client instance.

        Returns:
            MEModelWorkflowContext populated with template parameters, rheobase,
            optional Rin, and the output directory.
        """
        logger.info("Setting up MEModel validation for entity %s", entity_id)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Fetch metadata
        memodel = client.get_entity(entity_type=MEModel, entity_id=UUID(entity_id))

        # Calibration problems are configuration errors, not a broken artifact, so they
        # are resolved before the disqualify boundary below.
        calibration = getattr(memodel, "calibration_result", None)
        holding_current = _resolve_holding_current(calibration, self.validation_profile)
        threshold_current = calibration.threshold_current if calibration else None

        # A failed download may be transient (network, server), so it never disqualifies.
        downloaded = download_memodel(client, memodel=memodel, output_dir=str(self.output_dir))

        try:
            cell, simulator_config = self._build_cell(
                downloaded, entity_id, holding_current, threshold_current
            )
        except Exception:
            # The downloaded artifact cannot be built into a Cell, so no task can use
            # it: mark it disqualified, then re-raise so the run still fails.
            self._mark_disqualified(client, entity_id)
            raise

        rheobase = _resolve_rheobase(self.validation_profile, cell, threshold_current)

        # Compute Rin for profiles that use voltage-based currents. Reuse the
        # calibrated value when available so the workflow matches platform data;
        # otherwise use the same calculation as the legacy validation workflow.
        rin = self._resolve_rin(calibration, cell, rheobase)

        # Prepare output directory for figures
        cell_name = memodel.name or entity_id
        out_dir = self.output_dir / cell_name
        out_dir.mkdir(parents=True, exist_ok=True)

        if rin is None:
            logger.info("Setup complete. Rheobase=%.4f nA", rheobase)
        else:
            logger.info("Setup complete. Rheobase=%.4f nA, Rin=%.4f MOhm", rheobase, rin)

        return MEModelWorkflowContext(
            entity_id=entity_id,
            template_params=cell.template_params,
            rheobase=rheobase,
            rin=rin,
            simulator_config=simulator_config,
            out_dir=out_dir,
            extra={"cell": cell, "memodel": memodel},
        )

    @staticmethod
    def _mark_disqualified(client: Client, entity_id: str) -> None:
        """Set the MEModel to ``disqualified`` without masking the load error.

        Called while a load error is being handled. If the lifecycle update itself
        fails (e.g. the client may not edit this entity), that is logged here so the
        caller can still re-raise the original load error.
        """
        try:
            update_entity_lifecycle_status(
                client=client,
                entity_id=UUID(entity_id),
                entity_type=MEModel,
                lifecycle_status=EntityLifecycleStatus.disqualified,
            )
        except Exception:
            logger.exception("Could not mark MEModel %s as disqualified", entity_id)
        else:
            logger.info("MEModel %s marked as disqualified: it cannot be loaded", entity_id)

    def _build_cell(
        self,
        downloaded: DownloadedMEModel,
        entity_id: str,
        holding_current: float,
        threshold_current: float | None,
    ) -> tuple[Any, SimulatorConfig]:
        """Build a Cell from the downloaded artifact.

        Covers the HOC simulator contract, mechanism compilation and loading,
        morphology selection and Cell construction. A failure here means no task can
        use the artifact, which the caller turns into a ``disqualified`` status.
        """
        hoc_config = extract_simulator_config_from_hoc(downloaded.hoc_path)
        if hoc_config is None:
            simulator_config = self.validation_profile.simulator_config_fallback
            logger.warning(
                "HOC %s has no celsius/v_init declarations; using explicit profile "
                "fallback celsius=%s, v_init=%s",
                downloaded.hoc_path,
                simulator_config.celsius,
                simulator_config.v_init,
            )
        else:
            simulator_config = hoc_config
        logger.info(
            "Using simulator configuration celsius=%s, v_init=%s for %s",
            simulator_config.celsius,
            simulator_config.v_init,
            downloaded.hoc_path,
        )

        # Compile and explicitly load mechanisms before constructing the Cell.
        mechanisms_dir = Path(downloaded.mechanisms_dir).resolve()
        _compile_mechanisms(mechanisms_dir, self.output_dir)
        _load_compiled_mechanisms(self.output_dir)

        # Create Cell
        from bluecellulab.cell.core import Cell  # ruff: ignore[import-outside-top-level]
        from bluecellulab.circuit.circuit_access import (  # ruff: ignore[import-outside-top-level]
            EmodelProperties,
        )
        from bluecellulab.simulation.neuron_globals import (  # ruff: ignore[import-outside-top-level]
            set_neuron_globals,
        )

        set_neuron_globals(
            temperature=simulator_config.celsius,
            v_init=simulator_config.v_init,
        )

        emodel_properties = EmodelProperties(
            threshold_current=threshold_current or 0.1,
            holding_current=holding_current,
            AIS_scaler=1.0,
        )

        morphology_path = _select_morphology_path(downloaded, entity_id)

        cell = Cell(
            template_path=downloaded.hoc_path,
            morphology_path=morphology_path,
            template_format="v6",
            emodel_properties=emodel_properties,
        )
        _verify_simulator_configuration(simulator_config)

        return cell, simulator_config

    def _resolve_rin(self, calibration: Any, cell: Any, rheobase: float) -> float | None:
        """Return Rin for profiles that need it, or None when not required.

        Reuses the calibrated value when present; otherwise computes it as the legacy
        workflow did. This runs after the Cell is built, so it is not part of the
        load/disqualify boundary: a model that loads but yields an unusable Rin is a
        configuration error, not an unloadable artifact.
        """
        if not self.validation_profile.requires_rin:
            return None

        from bluecellulab.tools import (  # ruff: ignore[import-outside-top-level]
            calculate_input_resistance,
        )

        rin = None
        calibrated_rin = getattr(calibration, "rin", None)
        if calibrated_rin is not None:
            rin = float(calibrated_rin)

        if rin is None or not math.isfinite(rin) or rin <= 0.0:
            rin = calculate_input_resistance(
                template_path=cell.template_params.template_filepath,
                morphology_path=cell.template_params.morph_filepath,
                template_format=cell.template_params.template_format,
                emodel_properties=cell.template_params.emodel_properties,
                current_delta=-0.2 * rheobase,
            )

        if not math.isfinite(rin) or rin <= 0.0:
            message = (
                f"Validation profile '{self.validation_profile.profile_name}' "
                f"requires a positive finite Rin; got {rin!r}."
            )
            raise InvalidValidationContextError(message)
        return rin

    def get_tests(self, context: MEModelWorkflowContext) -> list[ValidationTest]:
        """Return profile-provided tests plus any custom tests.

        Args:
            context: The workflow context from setup().

        Returns:
            List of validation test instances for the selected profile.
        """
        self.validation_profile.validate_context(context)
        tests = self.validation_profile.build_tests(context)
        tests.extend(self.custom_tests)
        return tests

    def run(self, context: MEModelWorkflowContext) -> list[TestResult]:
        """Execute all parametric tests and collect test results.

        Args:
            context: The workflow context from setup().

        Returns:
            List of TestResult results.
        """
        tests = self.get_tests(context)
        if context.rheobase is None or context.out_dir is None:
            raise InvalidValidationContextError

        # Multiprocessing tests (IV/FI curves) spawn workers that reinitialize
        # NEURON and auto-load the compiled mechanisms from the current working
        # directory. Run with the output directory as CWD so the workers find
        # the library compiled during setup; the change is scoped and restored
        # on exit so it does not leak into later work in the same process.
        test_results = []
        with chdir(self.output_dir):
            for test in tests:
                result = test.run(
                    context.template_params,
                    context.rheobase,
                    context.out_dir,
                )
                test_results.append(result)
        return test_results

    def register(  # ruff: ignore[no-self-use]
        self,
        test_results: list[TestResult],
        context: MEModelWorkflowContext,
        client: Client,
        *,
        overwrite_existing: bool = False,
    ) -> list:
        """Register all test results as ValidationResult entities.

        Args:
            test_results: List of TestResult from run().
            context: The workflow context.
            client: entitysdk Client instance.
            overwrite_existing: If True, update matching results in place; otherwise
                skip them.

        Returns:
            List of RegisteredResult objects.
        """
        return register_outcomes(
            client=client,
            test_results=test_results,
            validated_entity_id=context.entity_id,
            out_dir=context.out_dir,
            overwrite_existing=overwrite_existing,
        )
