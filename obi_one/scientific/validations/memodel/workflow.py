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
import os
import subprocess  # ruff: ignore[suspicious-subprocess-import]
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from bluecellulab.validation.base import TestResult, ValidationTest
from entitysdk import Client
from entitysdk.downloaders.memodel import download_memodel
from entitysdk.models import MEModel

from obi_one.scientific.validations.base import (
    InvalidValidationContextError,
    ValidationWorkflow,
    WorkflowContext,
)
from obi_one.scientific.validations.memodel.presets import spiking_preset
from obi_one.scientific.validations.registration import register_outcomes

logger = logging.getLogger(__name__)


@dataclass
class MEModelWorkflowContext(WorkflowContext):
    """Workflow context for MEModel parametric validation.

    Extends the generic WorkflowContext with electrophysiology-specific fields
    required by BlueCelluLab parametric tests.

    Attributes:
        template_params: BlueCelluLab TemplateParams for creating the cell.
        rheobase: The rheobase (threshold) current in nA.
        out_dir: Output directory for figures and artifacts.
    """

    template_params: Any = None
    rheobase: float | None = None
    out_dir: Path | None = None


class MEModelValidationWorkflow(ValidationWorkflow[MEModelWorkflowContext]):
    """Validation workflow for MEModel (SimulatableNeuron) entities.

    Attributes:
        output_dir: Base directory for validation output (figures, details).
        custom_tests: Additional tests to run beyond the default presets.
    """

    def __init__(
        self,
        output_dir: str | Path = "./memodel_validation_output",
        custom_tests: list[ValidationTest] | None = None,
    ) -> None:
        """Initialize the MEModel validation workflow.

        Args:
            output_dir: Base directory for validation output.
            custom_tests: Additional tests to run beyond the default presets.
        """
        self.output_dir = Path(output_dir).resolve()
        self.custom_tests = custom_tests or []

    def setup(self, entity_id: str, client: Client) -> MEModelWorkflowContext:
        """Download MEModel, compile mechanisms, create Cell, compute rheobase.

        Args:
            entity_id: MEModel entity ID on the platform.
            client: entitysdk Client instance.

        Returns:
            MEModelWorkflowContext populated with template_params, rheobase, and out_dir.
        """
        logger.info("Setting up MEModel validation for entity %s", entity_id)

        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Fetch metadata
        memodel = client.get_entity(entity_type=MEModel, entity_id=UUID(entity_id))

        # Download assets into absolute output_dir
        downloaded = download_memodel(client, memodel=memodel, output_dir=str(self.output_dir))

        # Compile mechanisms using absolute path
        mechanisms_dir = Path(downloaded.mechanisms_dir).resolve()
        logger.info("Compiling mechanisms from: %s", mechanisms_dir)
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            ["nrnivmodl", str(mechanisms_dir)],  # ruff: ignore[start-process-with-partial-path]
            capture_output=True,
            text=True,
            cwd=str(self.output_dir),
            check=False,
        )
        if result.returncode != 0:
            logger.warning(
                "nrnivmodl failed:\nstdout: %s\nstderr: %s", result.stdout, result.stderr
            )

        # Change to output_dir so NEURON can find the compiled mechanisms
        os.chdir(self.output_dir)

        # Create Cell
        from bluecellulab.cell.core import Cell  # ruff: ignore[import-outside-top-level]
        from bluecellulab.circuit.circuit_access import (  # ruff: ignore[import-outside-top-level]
            EmodelProperties,
        )
        from bluecellulab.simulation.neuron_globals import (  # ruff: ignore[import-outside-top-level]
            set_neuron_globals,
        )
        from bluecellulab.tools import calculate_rheobase  # ruff: ignore[import-outside-top-level]

        set_neuron_globals(temperature=34.0, v_init=-80.0)

        # Get holding/threshold from calibration if available
        calibration = getattr(memodel, "calibration_result", None)
        holding_current = calibration.holding_current if calibration else 0.0
        threshold_current = calibration.threshold_current if calibration else None

        emodel_properties = EmodelProperties(
            threshold_current=threshold_current or 0.1,
            holding_current=holding_current,
            AIS_scaler=1.0,
        )

        cell = Cell(
            template_path=downloaded.hoc_path,
            morphology_path=downloaded.morphology_path,
            template_format="v6",
            emodel_properties=emodel_properties,
        )

        # Compute rheobase if not from calibration
        if threshold_current:
            rheobase = threshold_current
        else:
            rheobase = calculate_rheobase(
                cell=cell, section="soma[0]", segx=0.5, threshold_voltage=-40.0
            )

        # Prepare output directory for figures
        cell_name = memodel.name or entity_id
        out_dir = self.output_dir / cell_name
        out_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Setup complete. Rheobase=%.4f nA", rheobase)

        return MEModelWorkflowContext(
            entity_id=entity_id,
            template_params=cell.template_params,
            rheobase=rheobase,
            out_dir=out_dir,
            extra={"cell": cell, "memodel": memodel},
        )

    def get_tests(self, context: MEModelWorkflowContext) -> list[ValidationTest]:
        """Return default OBI presets plus any custom tests.

        Args:
            context: The workflow context from setup().

        Returns:
            List of ValidationTest instances.
        """
        _ = context  # intentionally unused
        tests: list[ValidationTest] = [
            spiking_preset(),
        ]
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

        test_results = []
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
        skip_if_exists: bool = True,
    ) -> list:
        """Register all test results as ValidationResult entities.

        Args:
            test_results: List of TestResult from run().
            context: The workflow context.
            client: entitysdk Client instance.
            skip_if_exists: Skip registration if result already exists.

        Returns:
            List of RegisteredResult objects.
        """
        return register_outcomes(
            client=client,
            test_results=test_results,
            validated_entity_id=context.entity_id,
            out_dir=context.out_dir,
            skip_if_exists=skip_if_exists,
        )
