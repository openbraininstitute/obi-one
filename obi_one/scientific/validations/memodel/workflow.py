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
import subprocess
from pathlib import Path

from entitysdk import Client
from entitysdk.downloaders.memodel import download_memodel
from entitysdk.models import MEModel

from bluecellulab.validation.base import ValidationTest

from obi_one.scientific.validations.base import ValidationWorkflow, WorkflowContext
from obi_one.scientific.validations.memodel.presets import spiking_preset
from obi_one.scientific.validations.registration import register_outcomes

logger = logging.getLogger(__name__)


class MEModelValidationWorkflow(ValidationWorkflow):
    """Validation workflow for MEModel (SimulatableNeuron) entities.

    Attributes:
        output_dir: Base directory for validation output (figures, details).
        custom_tests: Additional tests to run beyond the default presets.
    """

    def __init__(
        self,
        output_dir: str | Path = "./memodel_validation_output",
        custom_tests: list[ValidationTest] | None = None,
    ):
        self.output_dir = Path(output_dir).resolve()
        self.custom_tests = custom_tests or []

    def setup(self, entity_id: str, client: Client) -> WorkflowContext:
        """Download MEModel, compile mechanisms, create Cell, compute rheobase.

        Args:
            entity_id: MEModel entity ID on the platform.
            client: entitysdk Client instance.

        Returns:
            WorkflowContext populated with template_params, rheobase, and out_dir.
        """
        logger.info(f"Setting up MEModel validation for entity {entity_id}")

        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Fetch metadata
        memodel = client.get_entity(entity_type=MEModel, entity_id=entity_id)

        # Download assets into absolute output_dir
        downloaded = download_memodel(client, memodel=memodel, output_dir=str(self.output_dir))

        # Compile mechanisms using absolute path
        mechanisms_dir = Path(downloaded.mechanisms_dir).resolve()
        logger.info(f"Compiling mechanisms from: {mechanisms_dir}")
        result = subprocess.run(
            ["nrnivmodl", str(mechanisms_dir)],
            capture_output=True,
            text=True,
            cwd=str(self.output_dir),
        )
        if result.returncode != 0:
            logger.warning(f"nrnivmodl failed:\nstdout: {result.stdout}\nstderr: {result.stderr}")

        # Change to output_dir so NEURON can find the compiled mechanisms
        os.chdir(self.output_dir)

        # Create Cell
        from bluecellulab.cell.core import Cell
        from bluecellulab.circuit.circuit_access import EmodelProperties
        from bluecellulab.simulation.neuron_globals import set_neuron_globals
        from bluecellulab.tools import calculate_rheobase

        set_neuron_globals(temperature=34.0, v_init=-80.0)

        # Get holding/threshold from calibration if available
        calibration = getattr(memodel, 'calibration_result', None)
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

        logger.info(f"Setup complete. Rheobase={rheobase:.4f} nA")

        return WorkflowContext(
            entity_id=entity_id,
            template_params=cell.template_params,
            rheobase=rheobase,
            out_dir=out_dir,
            extra={"cell": cell, "memodel": memodel},
        )

    def get_tests(self, context: WorkflowContext) -> list[ValidationTest]:
        """Return default OBI presets plus any custom tests.

        Args:
            context: The workflow context from setup().

        Returns:
            List of ValidationTest instances.
        """
        tests: list[ValidationTest] = [
            spiking_preset(),
        ]
        tests.extend(self.custom_tests)
        return tests

    def register(
        self,
        outcomes,
        context: WorkflowContext,
        client: Client,
        skip_if_exists: bool = True,
    ):
        """Register all outcomes as ValidationResult entities.

        Args:
            outcomes: List of ValidationOutcome from run().
            context: The workflow context.
            client: entitysdk Client instance.
            skip_if_exists: Skip registration if result already exists.

        Returns:
            List of RegisteredResult objects.
        """
        return register_outcomes(
            client=client,
            outcomes=outcomes,
            validated_entity_id=context.entity_id,
            out_dir=context.out_dir,
            skip_if_exists=skip_if_exists,
        )
